"""K 线 / 逐笔的统一入口：双源 fallback + 增量缓存。

- ``fetch_kline``：腾讯优先、东财兜底。
  腾讯没有季 / 半年 / 年 / 120 分钟，这些周期会直接走东财。
- ``fetch_ticks``：东财优先、腾讯兜底。

K 线磁盘缓存历史根；交易时段只拉最新几根合并；休市走缓存，到期用尾盘校验
（已定型的 K 对不上则当复权 / 缺口，整段重拉）。

两边返回字段不完全一样，K 线 / 逐笔会先收成同一套再给 API / 统计用。
不提供分时 trends2。区间涨跌见 ``company.statistics.period_returns``。
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime
from typing import Any

from core.cache import TtlCache
from core.codes import normalize_code
from core.fmt import to_float
from core.paths import KLINE_CACHE_DIR, ensure_cache_dirs
from company.line.eastmoney_kline import MINUTE_PERIODS as EM_MINUTE_PERIODS
from company.line.eastmoney_kline import fetch_line as fetch_eastmoney_line
from company.line.eastmoney_ticks import fetch_ticks as fetch_eastmoney_ticks
from company.line.session import is_cn_market_live
from company.line.tencent_kline import fetch_line as fetch_tencent_line
from company.line.tencent_ticks import fetch_ticks as fetch_tencent_ticks

logger = logging.getLogger(__name__)

# 盘中合并结果短缓存，避免同一页多次请求各打一次尾盘。
KLINE_LIVE_TTL = 8
# 带 beg/end 的区间查询仍整段拉，短 TTL。
KLINE_RANGE_TTL = 120
# 非交易时段：到期后用最新几根核对是否要更新。
KLINE_VERIFY_TTL = 30 * 60
TICKS_TTL = 1

_KLINE_DISK_VERSION = 1
_KLINE_TAIL_DAY = 2
_KLINE_TAIL_MINUTE_MAX = 80
_MINUTE_PERIODS = frozenset(EM_MINUTE_PERIODS)
_PERIOD_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "120m": 120,
}

_kline_live_cache = TtlCache(KLINE_LIVE_TTL)
_kline_range_cache = TtlCache(KLINE_RANGE_TTL)
_ticks_cache = TtlCache(TICKS_TTL)
_kline_disk_lock = threading.Lock()


def _kline_payload(pack: dict[str, Any], *, source: str) -> dict[str, Any]:
    """去掉腾讯 / 东财各自多出来的字段，收成对外 K 线包。"""
    items = list(pack.get("items") or [])
    return {
        "code": pack.get("code") or "",
        "name": pack.get("name") or "",
        "period": pack.get("period") or "",
        "adjust": pack.get("adjust") or "",
        "pre_price": pack.get("pre_price"),
        "source": source or pack.get("source") or "",
        "count": len(items),
        "items": items,
    }


def _ticks_payload(pack: dict[str, Any], *, source: str) -> dict[str, Any]:
    """去掉腾讯 / 东财各自多出来的字段，收成对外逐笔包。最后一条即最新成交。"""
    items = list(pack.get("items") or [])
    last = items[-1] if items else {}
    return {
        "code": pack.get("code") or "",
        "name": pack.get("name") or "",
        "pre_price": pack.get("pre_price"),
        "last_time": last.get("time") or pack.get("last_time") or "",
        "last_price": last.get("price") if last else pack.get("last_price"),
        "day": pack.get("day") or "",
        "source": source or pack.get("source") or "",
        "count": len(items),
        "items": items,
    }


def _cache_get(cache: TtlCache, key: str, force: bool) -> Any | None:
    """force=True 跳过缓存，用于手动刷新。"""
    if force:
        return None
    return cache.get(key)


def _bar_time(item: dict[str, Any]) -> str:
    return str(item.get("time") or "").strip()


def _close_enough(left: Any, right: Any) -> bool:
    """已定型 K 的价格是否仍对得上。差太多视为复权或源站修正。"""
    a = to_float(left)
    b = to_float(right)
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    scale = max(abs(a), abs(b), 1e-9)
    return abs(a - b) <= max(0.01, 0.002 * scale)


def _same_sealed_bar(cached: dict[str, Any], remote: dict[str, Any]) -> bool:
    return all(
        _close_enough(cached.get(key), remote.get(key))
        for key in ("open", "close", "high", "low")
    )


def _public_kline(pack: dict[str, Any]) -> dict[str, Any]:
    items = list(pack.get("items") or [])
    return {
        "code": pack.get("code") or "",
        "name": pack.get("name") or "",
        "period": pack.get("period") or "",
        "adjust": pack.get("adjust") or "",
        "pre_price": pack.get("pre_price"),
        "source": pack.get("source") or "",
        "count": len(items),
        "items": items,
    }


def _slice_payload(pack: dict[str, Any], cap: int) -> dict[str, Any]:
    out = _public_kline(pack)
    items = out["items"]
    if cap > 0 and len(items) > cap:
        items = items[-cap:]
        out["items"] = items
        out["count"] = len(items)
    return out


def _empty_kline(code: str, period: str, adjust: str) -> dict[str, Any]:
    return {
        "code": code,
        "name": "",
        "period": period,
        "adjust": adjust,
        "pre_price": None,
        "source": "",
        "count": 0,
        "items": [],
    }


def _disk_key_part(value: str, fallback: str) -> str:
    return re.sub(r"[^\w.-]+", "_", (value or "").strip()) or fallback


def _kline_disk_path(code: str, period: str, adjust: str):
    ensure_cache_dirs()
    name = (
        f"{_disk_key_part(code, 'unknown')}"
        f"_{_disk_key_part(period, 'day')}"
        f"_{_disk_key_part(adjust, 'qfq')}.json"
    )
    return KLINE_CACHE_DIR / name


def _load_kline_disk(code: str, period: str, adjust: str) -> dict[str, Any] | None:
    path = _kline_disk_path(code, period, adjust)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(payload.get("version") or 0) != _KLINE_DISK_VERSION:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return None
    return {
        "code": data.get("code") or code,
        "name": data.get("name") or "",
        "period": data.get("period") or period,
        "adjust": data.get("adjust") or adjust,
        "pre_price": data.get("pre_price"),
        "source": data.get("source") or "",
        "count": len(items),
        "items": list(items),
        "verified_at": float(payload.get("verified_at") or payload.get("cached_at") or 0),
    }


def _save_kline_disk(code: str, period: str, adjust: str, pack: dict[str, Any]) -> None:
    items = pack.get("items") or []
    if not items:
        return
    path = _kline_disk_path(code, period, adjust)
    data = {
        "code": pack.get("code") or code,
        "name": pack.get("name") or "",
        "period": pack.get("period") or period,
        "adjust": pack.get("adjust") or adjust,
        "pre_price": pack.get("pre_price"),
        "source": pack.get("source") or "",
        "items": list(items),
    }
    body = {
        "version": _KLINE_DISK_VERSION,
        "cached_at": time.time(),
        "verified_at": time.time(),
        "data": data,
    }
    with _kline_disk_lock:
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def _fetch_remote_kline(
    code: str,
    *,
    period: str,
    adjust: str | int,
    limit: int,
    beg: str = "",
    end: str = "",
) -> dict[str, Any]:
    """腾讯优先、东财兜底。空包不带 source。"""
    kwargs = {
        "period": period,
        "adjust": adjust,
        "limit": limit,
        "beg": beg,
        "end": end,
    }
    pack: dict[str, Any] = {}
    try:
        pack = fetch_tencent_line(code, **kwargs)
        if pack.get("items"):
            return _kline_payload(pack, source="tencent")
    except ValueError as exc:
        if "不支持" not in str(exc):
            logger.info("tencent kline skip %s: %s", code, exc)
    except Exception as exc:  # noqa: BLE001
        logger.info("tencent kline failed %s: %s", code, exc)

    try:
        pack = fetch_eastmoney_line(code, **kwargs)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.info("eastmoney kline failed %s: %s", code, exc)
        pack = {}

    source = "eastmoney" if pack.get("items") else ""
    result = _kline_payload(pack if isinstance(pack, dict) else {}, source=source)
    if not result.get("code"):
        result["code"] = code
    if not result.get("period"):
        result["period"] = (period or "day").strip().lower()
    if not result.get("adjust"):
        result["adjust"] = str(adjust if adjust is not None else "qfq").strip().lower()
    return result


def _tail_limit(period: str, last_time: str) -> int:
    """盘中 / 校验时拉多少根尾盘。日线 2 根；分钟按缺口估，上限 80。"""
    key = (period or "day").strip().lower()
    if key not in _MINUTE_PERIODS:
        return _KLINE_TAIL_DAY
    step = _PERIOD_MINUTES.get(key) or 1
    parsed = _parse_bar_dt(last_time)
    if parsed is None:
        return min(_KLINE_TAIL_MINUTE_MAX, 16)
    delta_min = max(0.0, (datetime.now() - parsed).total_seconds() / 60.0)
    guessed = int(delta_min / step) + 4
    return max(4, min(_KLINE_TAIL_MINUTE_MAX, guessed))


def _parse_bar_dt(text: str) -> datetime | None:
    raw = (text or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19] if len(raw) >= 19 else raw, fmt)
        except ValueError:
            continue
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 12:
        try:
            return datetime.strptime(digits[:12], "%Y%m%d%H%M")
        except ValueError:
            return None
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d")
        except ValueError:
            return None
    return None


def _merge_tail(
    cached_items: list[dict[str, Any]],
    tail_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, str]:
    """把尾盘合并进缓存。返回 ``(items, reason)``；items 为 None 表示需要整段重拉。"""
    if not tail_items:
        return list(cached_items), "empty-tail"
    if not cached_items:
        return list(tail_items), "ok"

    cache_by_time = {_bar_time(item): item for item in cached_items if _bar_time(item)}
    last_tail_time = _bar_time(tail_items[-1])
    overlap = False
    for item in tail_items:
        stamp = _bar_time(item)
        if not stamp or stamp not in cache_by_time:
            continue
        overlap = True
        if stamp == last_tail_time:
            continue
        if not _same_sealed_bar(cache_by_time[stamp], item):
            return None, "adjust"

    first_tail_time = _bar_time(tail_items[0])
    last_cache_time = _bar_time(cached_items[-1])
    if not overlap:
        if first_tail_time and last_cache_time and first_tail_time > last_cache_time:
            return None, "gap"
        return None, "no-overlap"

    kept = [item for item in cached_items if _bar_time(item) < first_tail_time]
    return kept + list(tail_items), "ok"


def _refresh_with_tail(
    stored: dict[str, Any],
    *,
    code: str,
    period: str,
    adjust: str | int,
    disk_adjust: str,
    cap: int,
) -> dict[str, Any]:
    """用最新几根更新缓存；对不上则整段重拉。尾盘失败则退回旧缓存。"""
    items = list(stored.get("items") or [])
    last_time = _bar_time(items[-1]) if items else ""
    tail_n = _tail_limit(period, last_time)
    tail = _fetch_remote_kline(code, period=period, adjust=adjust, limit=tail_n)
    tail_items = list(tail.get("items") or [])
    if not tail_items:
        logger.info("kline tail empty %s %s, keep cache", code, period)
        return _public_kline(stored)

    merged, reason = _merge_tail(items, tail_items)
    if merged is None:
        fetch_n = max(cap, len(items))
        logger.info("kline cache refresh %s %s: %s", code, period, reason)
        result = _fetch_remote_kline(code, period=period, adjust=adjust, limit=fetch_n)
        if result.get("items"):
            _save_kline_disk(code, period, disk_adjust, result)
        return _public_kline(result)

    result = {
        "code": tail.get("code") or stored.get("code") or code,
        "name": tail.get("name") or stored.get("name") or "",
        "period": stored.get("period") or period,
        "adjust": stored.get("adjust") or disk_adjust,
        "pre_price": tail.get("pre_price")
        if tail.get("pre_price") is not None
        else stored.get("pre_price"),
        "source": tail.get("source") or stored.get("source") or "",
        "count": len(merged),
        "items": merged,
    }
    _save_kline_disk(code, period, disk_adjust, result)
    return _public_kline(result)


def load_kline_disk(
    code: str,
    *,
    period: str = "day",
    adjust: str | int = "qfq",
) -> dict[str, Any] | None:
    """只读磁盘日 K，不触发远程校验。历史回填用。"""
    code = normalize_code(code)
    if not code:
        return None
    period_key = (period or "day").strip().lower()
    fqt = str(adjust if adjust is not None else "qfq").strip().lower()
    return _load_kline_disk(code, period_key, fqt)


def fetch_kline(
    code: str,
    *,
    period: str = "day",
    adjust: str | int = "qfq",
    limit: int = 320,
    beg: str = "",
    end: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """拉取 K 线。腾讯优先，东财兜底。

    交易时段：历史根走磁盘，只补最新几根。
    非交易时段：整段走缓存，定期用尾盘校验。
    ``force=True`` 跳过缓存整段重拉。

    period: 1m|5m|15m|30m|60m|120m|day|week|month|quarter|halfyear|year
    adjust: none|qfq|hfq（或 0|1|2），默认前复权。
    """
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")

    period_key = (period or "day").strip().lower()
    fqt = str(adjust if adjust is not None else "qfq").strip().lower()
    cap = int(limit or 320)
    beg_s = (beg or "").replace("-", "").strip()
    end_s = (end or "").replace("-", "").strip()
    now = time.time()

    # 日期区间查询无法做「只补最新一根」，仍整段拉 + 短 TTL。
    if beg_s or end_s:
        cache_key = f"{code}:{period_key}:{fqt}:{cap}:{beg_s}:{end_s}"
        hit = _cache_get(_kline_range_cache, cache_key, force)
        if hit is not None:
            return hit
        result = _fetch_remote_kline(
            code, period=period, adjust=adjust, limit=cap, beg=beg_s, end=end_s
        )
        if result.get("items"):
            _kline_range_cache.put(cache_key, result, cached_at=now)
        return result

    mem_key = f"{code}:{period_key}:{fqt}"
    if not force:
        hit = _kline_live_cache.get(mem_key)
        if hit is not None:
            return _slice_payload(hit, cap)

    stored = None if force else _load_kline_disk(code, period_key, fqt)
    live = is_cn_market_live()

    if stored and len(stored.get("items") or []) >= cap:
        verified_at = float(stored.get("verified_at") or 0)
        if live:
            result = _refresh_with_tail(
                stored,
                code=code,
                period=period_key,
                adjust=adjust,
                disk_adjust=fqt,
                cap=cap,
            )
        elif now - verified_at < KLINE_VERIFY_TTL:
            result = _public_kline(stored)
        else:
            result = _refresh_with_tail(
                stored,
                code=code,
                period=period_key,
                adjust=adjust,
                disk_adjust=fqt,
                cap=cap,
            )
        if result.get("items"):
            _kline_live_cache.put(mem_key, result, cached_at=now)
            return _slice_payload(result, cap)

    result = _fetch_remote_kline(code, period=period, adjust=adjust, limit=cap)
    if not result.get("code"):
        result["code"] = code
    if not result.get("period"):
        result["period"] = period_key
    if result.get("items"):
        _save_kline_disk(code, period_key, fqt, result)
        _kline_live_cache.put(mem_key, result, cached_at=now)
    elif stored and stored.get("items"):
        return _slice_payload(stored, cap)
    elif not result.get("items"):
        return result if result else _empty_kline(code, period_key, fqt)
    return _slice_payload(result, cap)


def fetch_ticks(
    code: str,
    *,
    pos: int | str = 0,
    force: bool = False,
) -> dict[str, Any]:
    """拉取当日成交明细。东财优先，腾讯兜底。

    pos=0 当天全部；pos=-20（或 20）最近 20 笔。
    """
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")

    cache_key = f"{code}:{pos}"
    now = time.time()
    hit = _cache_get(_ticks_cache, cache_key, force)
    if hit is not None:
        return hit

    pack: dict[str, Any] = {}
    try:
        pack = fetch_eastmoney_ticks(code, pos=pos)
        if pack.get("items"):
            result = _ticks_payload(pack, source="eastmoney")
            _ticks_cache.put(cache_key, result, cached_at=now)
            return result
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.info("eastmoney ticks failed %s: %s", code, exc)

    try:
        pack = fetch_tencent_ticks(code, pos=pos)
    except Exception as exc:  # noqa: BLE001
        logger.info("tencent ticks failed %s: %s", code, exc)
        pack = {}

    source = "tencent" if pack.get("items") else ""
    result = _ticks_payload(pack if isinstance(pack, dict) else {}, source=source)
    if not result.get("code"):
        result["code"] = code
    _ticks_cache.put(cache_key, result, cached_at=now)
    return result
