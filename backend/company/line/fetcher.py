"""K 线 / 逐笔的统一入口：三源 fallback + 增量缓存。

- ``fetch_kline``：同花顺优先、腾讯其次、东财兜底。
  同花顺没有半年 K，该周期会直接走东财；腾讯没有季 / 半年 / 年 / 120 分钟，这些周期会直接走东财。
- ``fetch_ticks``：同花顺优先、东财其次、腾讯兜底。
  盘中（09:15–15:31）全量查询覆盖当天文件，增量查询合并进文件；
  盘后 / 周末优先读该交易日文件，若未收齐到 15:00 则再打一次远程补齐。

K 线磁盘缓存历史根；交易时段只拉最新几根合并；休市 / 午休走缓存，
只要自最近一次收盘后已校验过就不再打远程（force 除外；对不上复权 / 缺口仍整段重拉）。

各源返回字段不完全一样，K 线 / 逐笔会先收成同一套再给 API / 统计用。
不提供分时 trends2。区间涨跌见 ``company.statistics.quote.derived.period_returns``。
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
from core.paths import KLINE_CACHE_DIR, TICKS_CACHE_DIR, ensure_cache_dirs
from company.line.eastmoney.kline import MINUTE_PERIODS as EM_MINUTE_PERIODS
from company.line.eastmoney.kline import fetch_line as fetch_eastmoney_line
from company.line.eastmoney.ticks import fetch_ticks as fetch_eastmoney_ticks
from company.line.session import (
    cn_now,
    is_cn_market_live,
    is_cn_session_open,
    last_session_close,
    parse_session_day,
    session_day,
)
from company.line.tencent.kline import fetch_line as fetch_tencent_line
from company.line.tencent.ticks import fetch_ticks as fetch_tencent_ticks
from company.line.tonghuashun.hq_ticks import fetch_time_and_sales as fetch_ths_time_and_sales
from company.line.tonghuashun.kline import fetch_line as fetch_tonghuashun_line

logger = logging.getLogger(__name__)

# 盘中合并结果短缓存，避免同一页多次请求各打一次尾盘。
KLINE_LIVE_TTL = 8
# 带 beg/end 的区间查询仍整段拉，短 TTL。
KLINE_RANGE_TTL = 120
TICKS_TTL = 1

_KLINE_DISK_VERSION = 1
_TICKS_DISK_VERSION = 1
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
_ticks_disk_lock = threading.Lock()


# ---------------------------------------------------------------------------
# 通用小工具
# ---------------------------------------------------------------------------

def _cache_get(cache: TtlCache, key: str, force: bool) -> Any | None:
    """force=True 跳过缓存，用于手动刷新。"""
    if force:
        return None
    return cache.get(key)


def _disk_key_part(value: str, fallback: str) -> str:
    return re.sub(r"[^\w.-]+", "_", (value or "").strip()) or fallback


# ---------------------------------------------------------------------------
# K 线
# ---------------------------------------------------------------------------

def _kline_payload(pack: dict[str, Any], *, source: str = "") -> dict[str, Any]:
    """去掉各源多出来的字段，收成对外 K 线包。source 非空则覆盖。"""
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


def _slice_payload(pack: dict[str, Any], cap: int) -> dict[str, Any]:
    out = _kline_payload(pack)
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


# 按优先级排列的 K 线源。东财支持全周期放最后兜底，其 ValueError
# 说明参数本身有问题（无效代码等），直接抛给调用方。
_KLINE_SOURCES: tuple[tuple[str, Any, bool], ...] = (
    ("tonghuashun", fetch_tonghuashun_line, False),
    ("tencent", fetch_tencent_line, False),
    ("eastmoney", fetch_eastmoney_line, True),
)


def _fetch_remote_kline(
    code: str,
    *,
    period: str,
    adjust: str | int,
    limit: int,
    beg: str = "",
    end: str = "",
) -> dict[str, Any]:
    """按 ``_KLINE_SOURCES`` 顺序打远程，首个有数据的源即返回。空包不带 source。"""
    kwargs = {
        "period": period,
        "adjust": adjust,
        "limit": limit,
        "beg": beg,
        "end": end,
    }
    for source, func, reraise in _KLINE_SOURCES:
        try:
            pack = func(code, **kwargs)
        except ValueError as exc:
            if reraise:
                raise
            # “不支持”说明该源没这个周期，静默过到下一个；其他 ValueError 记一笔。
            if "不支持" not in str(exc):
                logger.info("%s kline skip %s: %s", source, code, exc)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.info("%s kline failed %s: %s", source, code, exc)
            continue
        if isinstance(pack, dict) and pack.get("items"):
            return _kline_payload(pack, source=source)

    return _empty_kline(
        code,
        (period or "day").strip().lower(),
        str(adjust if adjust is not None else "qfq").strip().lower(),
    )


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
        return _kline_payload(stored)

    merged, reason = _merge_tail(items, tail_items)
    if merged is None:
        fetch_n = max(cap, len(items))
        logger.info("kline cache refresh %s %s: %s", code, period, reason)
        result = _fetch_remote_kline(code, period=period, adjust=adjust, limit=fetch_n)
        if result.get("items"):
            _save_kline_disk(code, period, disk_adjust, result)
        return _kline_payload(result)

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
    return _kline_payload(result)


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
    """拉取 K 线。同花顺优先，腾讯其次，东财兜底。

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
        # 非交易时段：收盘后已校验过的磁盘缓存直接用，避免隔半小时又全市场尾盘刷新。
        sealed_after_close = verified_at >= last_session_close().timestamp()
        if not live and sealed_after_close:
            result = _kline_payload(stored)
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
        return _empty_kline(code, period_key, fqt)
    return _slice_payload(result, cap)


# ---------------------------------------------------------------------------
# 逐笔
# ---------------------------------------------------------------------------

def _ticks_payload(pack: dict[str, Any], *, source: str, cached: bool = False) -> dict[str, Any]:
    """去掉各源多出来的字段，收成对外逐笔包。最后一条即最新成交。"""
    items = list(pack.get("items") or [])
    last = items[-1] if items else {}
    day = str(pack.get("day") or pack.get("session_day") or "")
    return {
        "code": pack.get("code") or "",
        "name": pack.get("name") or "",
        "pre_price": pack.get("pre_price"),
        "last_time": last.get("time") or pack.get("last_time") or "",
        "last_price": last.get("price") if last else pack.get("last_price"),
        "day": day,
        "source": source or pack.get("source") or "",
        "count": len(items),
        "items": items,
        "cached": cached,
        "session_day": str(pack.get("session_day") or day),
        "cached_at": str(pack.get("cached_at") or ""),
    }


def _ensure_ticks_day(result: dict[str, Any]) -> dict[str, Any]:
    """远程逐笔包补上当天 session_day，避免下游按空日期归档。"""
    if not result.get("day"):
        result["day"] = session_day().isoformat()
        result["session_day"] = result["day"]
    return result


def _normalize_ticks_pos(pos: int | str | None) -> int:
    """0=当天全部；负数=最近 N 笔。正数会收成负数。"""
    if pos is None or pos == "":
        return 0
    if isinstance(pos, str):
        text = pos.strip()
        if not text:
            return 0
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError("pos 须为整数，0=当天全部，负数=最近 N 笔") from exc
    else:
        value = int(pos)
    if value > 0:
        value = -value
    return value


def _slice_ticks_pos(pack: dict[str, Any], pos: int) -> dict[str, Any]:
    if pos >= 0:
        return pack
    items = list(pack.get("items") or [])
    n = abs(pos)
    if n <= 0 or len(items) <= n:
        return pack
    sliced = items[-n:]
    last = sliced[-1] if sliced else {}
    out = dict(pack)
    out["items"] = sliced
    out["count"] = len(sliced)
    out["last_time"] = last.get("time") or out.get("last_time") or ""
    out["last_price"] = last.get("price") if last else out.get("last_price")
    return out


def _ticks_time_key(value: Any) -> str:
    """统一成 HH:MM:SS，便于比较是否已收到收盘附近成交。"""
    text = str(value or "").strip()
    if len(text) == 5 and text[2] == ":":
        return f"{text}:00"
    return text


def _ticks_looks_complete(pack: dict[str, Any] | None) -> bool:
    """盘后文件是否至少覆盖到常规收盘 15:00。"""
    if not pack:
        return False
    items = pack.get("items") or []
    if not items:
        return False
    last = _ticks_time_key(items[-1].get("time") or pack.get("last_time"))
    return last >= "15:00:00"


def _tick_seq(row: dict[str, Any]) -> int:
    try:
        return int(row.get("seq") or 0)
    except (TypeError, ValueError):
        return 0


def _tick_row_key(row: dict[str, Any], *, relaxed: bool = False) -> str:
    time = str(row.get("time") or "")
    price = to_float(row.get("price"))
    volume = to_float(row.get("volume")) or 0.0
    base = f"{time}|{price}|{volume}"
    if relaxed:
        return base
    return f"{base}|{row.get('count', '')}|{row.get('seq', '')}"


def _merge_tick_items(
    current: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把增量逐笔接到已有全日列表后面（与前端 mergeTickItems 对齐）。"""
    if not incoming:
        return current
    if not current:
        return list(incoming)

    def find_overlap(relaxed: bool) -> int:
        last_key = _tick_row_key(current[-1], relaxed=relaxed)
        for i in range(len(incoming) - 1, -1, -1):
            if _tick_row_key(incoming[i], relaxed=relaxed) == last_key:
                return i
        key_to_index = {
            _tick_row_key(row, relaxed=relaxed): i for i, row in enumerate(incoming)
        }
        for i in range(len(current) - 1, -1, -1):
            hit = key_to_index.get(_tick_row_key(current[i], relaxed=relaxed))
            if hit is not None:
                return hit
        return -1

    idx = find_overlap(False)
    if idx < 0:
        idx = find_overlap(True)
    if idx >= 0:
        return current + incoming[idx + 1:]

    cur_last = _ticks_time_key(current[-1].get("time"))
    inc_last = _ticks_time_key(incoming[-1].get("time"))
    if inc_last > cur_last:
        newer = [row for row in incoming if _ticks_time_key(row.get("time")) > cur_last]
        if newer:
            return current + newer
    if len(current) >= len(incoming):
        return current
    return list(incoming)


def _ticks_disk_path(code: str, day=None):
    ensure_cache_dirs()
    parsed = parse_session_day(day)
    iso = (parsed or session_day()).isoformat()
    return TICKS_CACHE_DIR / f"{_disk_key_part(code, 'unknown')}_{iso}.json"


def _empty_ticks(code: str, *, day: str = "") -> dict[str, Any]:
    iso = str(day or session_day().isoformat())
    return {
        "code": code,
        "name": "",
        "pre_price": None,
        "last_time": "",
        "last_price": None,
        "day": iso,
        "source": "",
        "count": 0,
        "items": [],
        "cached": False,
        "session_day": iso,
        "cached_at": "",
        "finalized": False,
    }


def _load_ticks_disk(code: str, day=None) -> dict[str, Any] | None:
    path = _ticks_disk_path(code, day)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(payload.get("version") or 0) != _TICKS_DISK_VERSION:
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
        "pre_price": data.get("pre_price"),
        "last_time": data.get("last_time") or "",
        "last_price": data.get("last_price"),
        "day": str(data.get("day") or payload.get("session_day") or ""),
        "source": data.get("source") or "",
        "count": len(items),
        "items": list(items),
        "cached": True,
        "session_day": str(payload.get("session_day") or data.get("day") or ""),
        "cached_at": str(payload.get("cached_at") or ""),
        "finalized": bool(payload.get("finalized")),
    }


def _save_ticks_disk(
    code: str,
    pack: dict[str, Any],
    *,
    finalized: bool | None = None,
) -> dict[str, Any]:
    items = list(pack.get("items") or [])
    if not items:
        return pack
    day = session_day()
    iso = day.isoformat()
    stamp = cn_now().isoformat()
    last = items[-1] if items else {}
    last_time = last.get("time") or pack.get("last_time") or ""
    last_price = last.get("price") if last else pack.get("last_price")
    data = {
        "code": pack.get("code") or code,
        "name": pack.get("name") or "",
        "pre_price": pack.get("pre_price"),
        "last_time": last_time,
        "last_price": last_price,
        "day": pack.get("day") or iso,
        "source": pack.get("source") or "",
        "items": items,
    }
    done = bool(finalized) if finalized is not None else bool(pack.get("finalized"))
    if done is False and _ticks_looks_complete({"items": items, "last_time": last_time}):
        # 已覆盖到收盘时刻时，盘中也可视为可定稿，减少盘后重复补齐
        done = not is_cn_session_open()
    body = {
        "version": _TICKS_DISK_VERSION,
        "session_day": iso,
        "cached_at": stamp,
        "finalized": done,
        "count": len(items),
        "data": data,
    }
    path = _ticks_disk_path(code)
    tmp = path.with_suffix(".json.tmp")
    text = json.dumps(body, ensure_ascii=False)
    with _ticks_disk_lock:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    out = dict(pack)
    out["day"] = data["day"]
    out["last_time"] = last_time
    out["last_price"] = last_price
    out["count"] = len(items)
    out["session_day"] = iso
    out["cached_at"] = stamp
    out["cached"] = False
    out["finalized"] = done
    return out


def _finalize_ticks_disk(code: str, pack: dict[str, Any]) -> dict[str, Any]:
    """盘后补齐结束（成功或无需更新）打标，避免反复打远程。"""
    return _save_ticks_disk(code, pack, finalized=True)


def _fetch_ths_ticks(code: str, *, pos: int = 0) -> dict[str, Any]:
    """同花顺秒级逐笔，收成统一逐笔包。失败返回空包，由上层继续兜底。

    无效代码的 ValueError 会直接抛给调用方。
    """
    limit = 0 if pos >= 0 else abs(pos)
    try:
        _, ts_items = fetch_ths_time_and_sales(code, count=limit if limit else 300)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.info("tonghuashun ticks failed %s: %s", code, exc)
        return _ticks_payload({}, source="")
    rows = [r for r in ts_items or [] if isinstance(r, dict)]
    rows.sort(key=lambda r: (str(r.get("time") or ""), _tick_seq(r)))
    if limit and len(rows) > limit:
        rows = rows[-limit:]
    if not rows:
        return _ticks_payload({}, source="")
    return _ticks_payload({"code": code, "items": rows}, source="tonghuashun")


def _fetch_remote_ticks(code: str, *, pos: int | str = 0) -> dict[str, Any]:
    """同花顺优先、东财其次、腾讯兜底。首个有数据的源即返回。"""
    pos_n = _normalize_ticks_pos(pos)

    result = _fetch_ths_ticks(code, pos=pos_n)
    if result.get("items"):
        return _ensure_ticks_day(result)

    try:
        pack: dict[str, Any] = fetch_eastmoney_ticks(code, pos=pos_n)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.info("eastmoney ticks failed %s: %s", code, exc)
        pack = {}
    if isinstance(pack, dict) and pack.get("items"):
        return _ensure_ticks_day(_ticks_payload(pack, source="eastmoney"))

    try:
        pack = fetch_tencent_ticks(code, pos=pos_n)
    except Exception as exc:  # noqa: BLE001
        logger.info("tencent ticks failed %s: %s", code, exc)
        pack = {}
    if not isinstance(pack, dict):
        pack = {}
    result = _ticks_payload(pack, source="tencent" if pack.get("items") else "")
    if not result.get("code"):
        result["code"] = code
    return _ensure_ticks_day(result)


def fetch_ticks(
    code: str,
    *,
    pos: int | str = 0,
    force: bool = False,
    day: str = "",
) -> dict[str, Any]:
    """拉取成交明细。同花顺优先，东财其次，腾讯兜底。

    pos=0 当天全部；pos=-20（或 20）最近 20 笔。
    不传 day：盘中覆盖 / 合并当天磁盘缓存；盘后优先读文件，未收齐到 15:00 时再补一次远程。
    传入历史 day：只读对应缓存，没有则空包。
    """
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")

    pos_n = _normalize_ticks_pos(pos)
    now = time.time()
    want_day = parse_session_day(day)
    today = session_day()
    if want_day is not None and want_day != today:
        stored = _load_ticks_disk(code, want_day)
        if stored:
            return _slice_ticks_pos(stored, pos_n)
        return _empty_ticks(code, day=want_day.isoformat())

    live = is_cn_session_open()
    stored = None if force else _load_ticks_disk(code)

    if stored and not live:
        if _ticks_looks_complete(stored) or stored.get("finalized"):
            return _slice_ticks_pos(stored, pos_n)
        # 盘后文件停在早盘/午盘（例如只缓存到 09:40）时补齐一次，避免分时成交显示不全
        result = _fetch_remote_ticks(code, pos=0)
        remote_items = list(result.get("items") or [])
        if remote_items:
            stored_items = list(stored.get("items") or [])
            remote_last = _ticks_time_key(result.get("last_time") or remote_items[-1].get("time"))
            stored_last = _ticks_time_key(stored.get("last_time") or (stored_items[-1].get("time") if stored_items else ""))
            if len(remote_items) > len(stored_items) or remote_last > stored_last:
                result = _save_ticks_disk(code, result, finalized=True)
                _ticks_cache.put(f"{code}:{pos_n}", result, cached_at=now)
                return _slice_ticks_pos(result, pos_n) if pos_n < 0 else result
        stored = _finalize_ticks_disk(code, stored)
        return _slice_ticks_pos(stored, pos_n)

    cache_key = f"{code}:{pos_n}"
    hit = _cache_get(_ticks_cache, cache_key, force)
    if hit is not None:
        return hit

    result = _fetch_remote_ticks(code, pos=pos_n)

    if pos_n == 0:
        if result.get("items"):
            result = _save_ticks_disk(code, result, finalized=not live)
        elif stored:
            return stored
    elif result.get("items"):
        # 盘中增量也合并进磁盘，避免收盘后只剩早盘那一段
        base = stored if stored and stored.get("items") else _load_ticks_disk(code)
        if base and base.get("items"):
            merged = _merge_tick_items(list(base["items"]), list(result["items"]))
            if len(merged) > len(base["items"]):
                pack = dict(base)
                pack["items"] = merged
                pack["source"] = result.get("source") or base.get("source") or ""
                if result.get("pre_price") is not None:
                    pack["pre_price"] = result.get("pre_price")
                _save_ticks_disk(code, pack, finalized=False)
    elif stored:
        return _slice_ticks_pos(stored, pos_n)

    _ticks_cache.put(cache_key, result, cached_at=now)
    return _slice_ticks_pos(result, pos_n) if pos_n < 0 else result
