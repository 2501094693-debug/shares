"""K 线 / 逐笔的统一入口：三源 fallback + 增量缓存。

- ``fetch_kline``：腾讯优先、东财其次、同花顺最后兜底（未登录跳过）。
  同花顺没有半年 K，该周期会直接走东财；腾讯没有季 / 半年 / 年 / 120 分钟，这些周期会直接走东财。
  缓存优先：先读磁盘全量，只远程拉缺失段（缺老段拉 [beg, cached_first)，缺新段刷新尾部），合并后存盘，不整段重拉（force/复权对不上除外）。
- ``fetch_ticks``：已登录同花顺优先；未登录先东财、腾讯兜底（跳过同花顺）。
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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
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

# 同花顺可用性缓存：未登录时跳过 THS、直走东财/腾讯，避免每次都打一次
# 必失败的扫码探活；登录成功后标记即时生效，TTL 内复查一次。
_THS_READY_TTL = 60.0
_ths_ready_cache: dict[str, Any] = {"ok": False, "at": 0.0}


def _ths_ready() -> bool:
    """同花顺已登录才返回 True；K线排第二，仅登录后参与fallback。"""
    try:
        from company.line.tonghuashun import auth as _ths_auth
    except Exception:
        return False
    if _ths_auth.is_authenticated():
        _ths_ready_cache["ok"] = True
        _ths_ready_cache["at"] = time.time()
        return True
    if time.time() - float(_ths_ready_cache.get("at") or 0) < _THS_READY_TTL:
        return bool(_ths_ready_cache.get("ok"))
    ok = bool(_ths_auth.ensure())
    _ths_ready_cache["ok"] = ok
    _ths_ready_cache["at"] = time.time()
    return ok


# 腾讯日 K 实际只给最近约 640 根，更早的会被截断；东财单次可给全历史。
# 大窗口（日线全历史回滚到上市）优先走东财，避免被腾讯短截断污染磁盘缓存。
_FULL_HISTORY_LIMIT = 640
_FULL_HISTORY_PERIODS = frozenset({"day", "week", "month", "quarter", "halfyear", "year"})


def _kline_source_order(
    period: str = "", limit: int = 0
) -> tuple[tuple[str, Any, bool], ...]:
    """K线优先腾讯，其次东财，同花顺最后兜底（未登录跳过）。"""
    base = _KLINE_SOURCES if _ths_ready() else tuple(s for s in _KLINE_SOURCES if s[0] != "tonghuashun")
    try:
        cap = int(limit or 0)
    except (TypeError, ValueError):
        cap = 0
    key = (period or "").strip().lower()
    if cap > _FULL_HISTORY_LIMIT and key in _FULL_HISTORY_PERIODS:
        order = {"tencent": 0, "eastmoney": 1, "tonghuashun": 2}
        return tuple(sorted(base, key=lambda s: order.get(s[0], 9)))
    return base

# 盘中合并结果短缓存，避免同一页多次请求各打一次尾盘。
KLINE_LIVE_TTL = 8
# 带 beg/end 的区间查询仍整段拉，短 TTL。
KLINE_RANGE_TTL = 120
TICKS_TTL = 1

_KLINE_DISK_VERSION = 2
_TICKS_DISK_VERSION = 2
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

# 同花顺 native 调用（klines / list_security_ticks）不接受超时参数，
# 周末或网络异常时可能长时间阻塞。用独立线程跑并限时等待，超时即视为
# 该源失败、继续 fallback，保证请求一定返回，孤儿线程由守护线程回收。
_THS_SOURCE_TIMEOUT = 25.0
_ths_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ths-src")


def _call_ths_source(label: str, code: str, func: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    fut = _ths_executor.submit(func, code, **kwargs)
    try:
        return fut.result(timeout=_THS_SOURCE_TIMEOUT)
    except FuturesTimeout:
        logger.warning("%s ths %s 超时(>%ss)，fallback 到下一源", label, code, _THS_SOURCE_TIMEOUT)
        return {}


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
    out["full_history"] = bool(pack.get("full_history"))
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
        "full_history": bool(payload.get("full_history") or (data.get("full_history"))),
    }


def _save_kline_disk(code: str, period: str, adjust: str, pack: dict[str, Any]) -> None:
    items = pack.get("items") or []
    if not items:
        return
    path = _kline_disk_path(code, period, adjust)
    try:
        old_body = json.loads(path.read_text(encoding="utf-8"))
        old_items = (old_body.get("data") or {}).get("items") or []
    except Exception:
        old_body, old_items = {}, []
    if old_items:
        # 防覆盖：新包只是一小段（如强制刷新 limit=320）时，与旧盘按日期并集，
        # 同日期新数据赢。这样再也不会把多年历史洗成 320 根。
        by_time = {str(b.get("time") or "")[:10]: b for b in old_items if str(b.get("time") or "")[:10]}
        for b in items:
            t = str(b.get("time") or "")[:10]
            if t:
                by_time[t] = b
        if len(by_time) > len(items):
            items = sorted(by_time.values(), key=lambda b: str(b.get("time") or ""))
            try:
                old_first = min(str(b.get("time") or "")[:10] for b in old_items if str(b.get("time") or "")[:10])
                old_last = max(str(b.get("time") or "")[:10] for b in old_items if str(b.get("time") or "")[:10])
                covers = str(items[0].get("time") or "")[:10] <= old_first and str(items[-1].get("time") or "")[:10] >= old_last
            except (ValueError, IndexError):
                covers = False
            pack = dict(pack)
            pack["full_history"] = bool(pack.get("full_history")) or (bool((old_body or {}).get("full_history")) and covers)
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
        "full_history": bool(pack.get("full_history")),
        "data": data,
    }
    with _kline_disk_lock:
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


# 按优先级排列的 K 线源。腾讯优先，东财其次，同花顺最后兜底。
_KLINE_SOURCES: tuple[tuple[str, Any, bool], ...] = (
    ("tencent", fetch_tencent_line, False),
    ("eastmoney", fetch_eastmoney_line, True),
    ("tonghuashun", fetch_tonghuashun_line, False),
)

# 东财/腾讯在这台网络下偶发 501/连接重置，各给一次重试机会，
# 避免一次抖动就直接fallback并污染磁盘缓存。
_SOURCE_RETRIES = 2


def _call_with_retry(func: Any, code: str, kwargs: dict[str, Any], *, label: str) -> dict[str, Any]:
    """调东财/腾讯：ValueError 直接抛（不支持的周期），其他异常重试一次后返回空包。"""
    last_exc: Exception | None = None
    for attempt in range(_SOURCE_RETRIES):
        try:
            return func(code, **kwargs)
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    if last_exc is not None:
        logger.info("%s failed %s (tried %d): %s", label, code, _SOURCE_RETRIES, last_exc)
    return {}


def _fetch_remote_kline(
    code: str,
    *,
    period: str,
    adjust: str | int,
    limit: int,
    beg: str = "",
    end: str = "",
) -> dict[str, Any]:
    """按腾讯->东财->同花顺(登录才用)排源。首个有数据的源即返回。

    传了 beg/end 时只接受落在区间内的源，忽略区间的源视为无数据继续 fallback。
    """
    beg_s = re.sub(r"\D", "", str(beg or ""))[:8]
    end_s = re.sub(r"\D", "", str(end or ""))[:8]
    kwargs = {
        "period": period,
        "adjust": adjust,
        "limit": limit,
        "beg": beg,
        "end": end,
    }
    for source, func, reraise in _kline_source_order(period, limit):
        try:
            if source == "tonghuashun":
                pack = _call_ths_source("kline", code, func, kwargs)
            else:
                pack = _call_with_retry(func, code, kwargs, label=f"{source} kline")
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
            if beg_s or end_s:
                lo = beg_s[:4] + "-" + beg_s[4:6] + "-" + beg_s[6:8] if len(beg_s) >= 8 else ""
                hi = end_s[:4] + "-" + end_s[4:6] + "-" + end_s[6:8] if len(end_s) >= 8 else ""
                ranged = [
                    it for it in pack["items"]
                    if (not lo or str(it.get("time") or "")[:10] >= lo)
                    and (not hi or str(it.get("time") or "")[:10] <= hi)
                ]
                # 该源不支持区间（如腾讯分钟线只给最近 N 根）时视为无数据，继续 fallback
                if not ranged:
                    continue
                pack = dict(pack)
                pack["items"] = ranged
            return _kline_payload(pack, source=source)

    return _empty_kline(
        code,
        (period or "day").strip().lower(),
        str(adjust if adjust is not None else "qfq").strip().lower(),
    )


_FULL_PAGE = 2000
_FULL_ROUNDS = 6

def _fetch_full_history(code, *, period, adjust, cap):
    out, seen, cur_end = [], set(), ""
    last_pack, sealed = {}, False
    from datetime import timedelta
    try:
        disk = _load_kline_disk(code, (period or 'day').strip().lower(),
                                str(adjust if adjust is not None else 'qfq').strip().lower())
        if disk and disk.get('items') and not disk.get('full_history'):
            out = list(disk['items'])
            for b in out:
                seen.add(str(b.get('time') or '')[:10])
            first = str(out[0].get('time') or '')[:10]
            try:
                cur_end = (datetime.strptime(first, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y%m%d')
            except ValueError:
                cur_end = ''
            last_pack = dict(disk)
    except Exception:
        pass
    _rounds = max(_FULL_ROUNDS, int(cap or 0) // 640 + 2)
    for _ in range(_rounds):
        if cur_end:
            time.sleep(3.0)
        try:
            pack = _fetch_remote_kline(code, period=period, adjust=adjust, limit=_FULL_PAGE, beg="", end=cur_end)
        except Exception as exc:
            logger.info("full history page failed %s end=%s: %s", code, cur_end, exc)
            break
        last_pack = pack
        items = sorted(pack.get("items") or [], key=lambda b: str(b.get("time") or ""))
        if not items:
            # 首选源在该端点之前已无数据 → 视为挖到上市
            sealed = True
            break
        fresh = [b for b in items if str(b.get("time") or "")[:10] not in seen]
        if not fresh:
            sealed = False
            if not out:
                last_pack = {"items": [], "count": 0, "source": "", "full_history": False}
            break
        for b in fresh:
            seen.add(str(b.get("time") or "")[:10])
        out = fresh + out
        try:
            if out:
                _save_kline_disk(code, (period or 'day').strip().lower(),
                                 str(adjust if adjust is not None else 'qfq').strip().lower(),
                                 {'code': code, 'items': sorted(out, key=lambda b: str(b.get('time') or '')),
                                  'source': pack.get('source') or '', 'full_history': False})
        except Exception:
            pass
        if len(out) >= cap:
            sealed = False
            break
        # 注：不再以 fresh<500 判定到顶（各源分页大小不一会误判，如东财在 600773 上
        # 2000-07-17 就只有 300 多根就断了），只认空页（到上市）/全重页（源头不认 end 参数）
        new_first = str(fresh[0].get("time") or "")[:10]
        new_last = str(fresh[-1].get("time") or "")[:10]
        old_first = str(out[-1].get("time") or "")[:10] if len(out) > len(fresh) else ""
        if new_last == old_first or (cur_end and new_last >= cur_end.replace("-", "")[:8] if False else False):
            pass
        first = str(fresh[0].get("time") or "")[:10]
        if cur_end and out and len(out) > len(fresh):
            prev_first = str(out[len(fresh)].get("time") or "")[:10] if len(out) > len(fresh) else ""
            if first >= prev_first:
                sealed = False
                break
        try:
            cur_end = (datetime.strptime(first, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y%m%d")
        except ValueError:
            break
    items = sorted(out, key=lambda b: str(b.get("time") or ""))
    items, _gsrc = _backfill_middle_gaps(items, code=code, period=period, adjust=adjust, cap=cap,
                                         stored_source=str((last_pack or {}).get("source") or ""))
    if _gsrc:
        last_pack["source"] = _gsrc
        try:
            _save_kline_disk(code, (period or 'day').strip().lower(),
                             str(adjust if adjust is not None else 'qfq').strip().lower(),
                             {'code': code, 'items': sorted(items, key=lambda b: str(b.get('time') or '')),
                              'source': _gsrc, 'full_history': False})
        except Exception:
            pass
    if cap > 0:
        items = items[-cap:]
    last_pack["items"] = items
    last_pack["count"] = len(items)
    last_pack["full_history"] = sealed
    return last_pack


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


def _merge_sorted(old: list[dict[str, Any]], seg: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 time 去重合并两段，只用于缺段补齐，不整段重排以外的事。"""
    have = {_bar_time(b) for b in old if _bar_time(b)}
    merged = list(old) + [b for b in (seg or []) if _bar_time(b) and _bar_time(b) not in have]
    merged.sort(key=lambda b: str(b.get("time") or ""))
    return merged


def _resolve_source(stored_src: str, remote_src: str, added_new: bool) -> str:
    """合并后 source 跟着真正提供新K线的那家走，避免旧牌子一直挂着。"""
    remote_src = (remote_src or "").strip()
    stored_src = (stored_src or "").strip()
    if added_new and remote_src:
        return remote_src
    return remote_src or stored_src


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
        # 缺段只补缺段：gap/adjust 时用日期区间拉 [cached_last, today]，不整段 limit 重拉
        logger.info("kline cache refresh %s %s: %s", code, period, reason)
        try:
            last_d = str((items[-1] or {}).get("time") or "")[:10].replace("-", "")
            seg = _fetch_remote_kline(code, period=period, adjust=adjust, limit=max(cap, 800), beg=last_d, end="")
            seg_items = list(seg.get("items") or [])
            if seg_items:
                fixed = _merge_sorted(items, seg_items)
                result = dict(seg)
                result["items"] = fixed
                result["count"] = len(fixed)
                result["source"] = _resolve_source(str(stored.get("source") or ""), str(seg.get("source") or ""), len(fixed) > len(items))
                _save_kline_disk(code, period, disk_adjust, result)
                return _kline_payload(result)
        except Exception as exc:
            logger.info("kline segment补尾 %s %s 失败: %s", code, period, exc)
        result = _fetch_remote_kline(code, period=period, adjust=adjust, limit=tail_n)
        if result.get("items"):
            fixed = _merge_sorted(items, list(result.get("items") or []))
            result = dict(result)
            result["items"] = fixed
            result["count"] = len(fixed)
            result["source"] = _resolve_source(str(stored.get("source") or ""), str(result.get("source") or ""), len(fixed) > len(items))
            _save_kline_disk(code, period, disk_adjust, result)
        return _kline_payload(result)

    merged, _gap_src = _backfill_middle_gaps(merged, code=code, period=period, adjust=adjust, cap=cap, stored_source=str(stored.get("source") or ""))
    result = {
        "code": tail.get("code") or stored.get("code") or code,
        "name": tail.get("name") or stored.get("name") or "",
        "period": stored.get("period") or period,
        "adjust": stored.get("adjust") or disk_adjust,
        "pre_price": tail.get("pre_price")
        if tail.get("pre_price") is not None
        else stored.get("pre_price"),
        "source": _gap_src or _resolve_source(str(stored.get("source") or ""), str(tail.get("source") or ""), len(merged) > len(items)),
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


_GAP_THRESH_DAYS = {"day": 45, "week": 200, "month": 600, "quarter": 1500, "halfyear": 2500, "year": 4000}
_gapcheck_at: dict[str, float] = {}


def _backfill_middle_gaps(items, *, code, period, adjust, cap, stored_source):
    """检测 K 线中间断段（如 2006→2023 这种大缺口）并远程补齐，顺带向前探头部
    （最早一根之前可能还有，如东财 600773 只到 2000-07，腾讯有 1996 起）。

    尾部合并只管尾巴，中间缺段以前永远修不好，这里补上。
    返回 (items, 新source|None)；12h 内同一标的只查一次，避免每次加载都多打网。
    """
    from datetime import timedelta
    period_key = (period or "day").strip().lower()
    thresh = _GAP_THRESH_DAYS.get(period_key, 0)
    if not thresh or not items or len(items) < 2:
        return items, None
    key = f"{code}:{period_key}:{str(adjust).lower()}"
    now = time.time()
    if now - _gapcheck_at.get(key, 0) < 12 * 3600:
        return items, None
    times = sorted({str(b.get("time") or "")[:10] for b in items if str(b.get("time") or "")[:10]})
    gaps = []
    for a, b in zip(times, times[1:]):
        try:
            delta = (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days
        except ValueError:
            continue
        if delta > thresh:
            gaps.append((a, b, delta))
    if gaps:
        logger.info("kline middle gaps %s %s: %s", code, period, [(a, b) for a, b, _ in gaps])
    gaps.sort(key=lambda g: -g[2])
    merged = list(items)
    seg_source = None
    added_total = 0
    for a, b, _d in gaps[:2]:
        try:
            _ga = datetime.strptime(a, "%Y-%m-%d") + timedelta(days=1)
            _gb = datetime.strptime(b, "%Y-%m-%d") - timedelta(days=1)
        except ValueError:
            continue
        # 大缺口按 ≤2 年一切（腾讯单次最多给 640 根，块太大一永远补不满），逐块拉
        chunks = []
        _cur = _ga
        while _cur <= _gb:
            _ce = min(_gb, _cur + timedelta(days=2 * 365))
            chunks.append((_cur.strftime("%Y%m%d"), _ce.strftime("%Y%m%d")))
            _cur = _ce + timedelta(days=1)
        for ga, gb in chunks:
            try:
                seg = _fetch_remote_kline(code, period=period, adjust=adjust,
                                          limit=2000, beg=ga, end=gb)
            except Exception as exc:
                logger.info("kline gapfill %s %s [%s,%s] failed: %s", code, period, ga, gb, exc)
                continue
            seg_items = list(seg.get("items") or [])
            if not seg_items:
                continue
            before = len(merged)
            merged = _merge_sorted(merged, seg_items)
            if len(merged) > before:
                added_total += len(merged) - before
                seg_source = str(seg.get("source") or "") or seg_source
    # 头部回补：最早一根之前可能还有（如东财 600773 只到 2000-07，腾讯有 1996 起）。
    # 最多向前探 3 页，探空即停。
    for _ in range(3):
        try:
            first_t = min(str(b.get("time") or "")[:10] for b in merged if str(b.get("time") or "")[:10])
        except ValueError:
            break
        try:
            he = (datetime.strptime(first_t, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y%m%d")
        except ValueError:
            break
        try:
            hpack = _fetch_remote_kline(code, period=period, adjust=adjust, limit=2000, beg="", end=he)
        except Exception as exc:
            logger.info("kline headfill %s %s end=%s failed: %s", code, period, he, exc)
            break
        older = [b for b in (hpack.get("items") or [])
                 if str(b.get("time") or "")[:10] and str(b.get("time") or "")[:10] < first_t
                 and str(b.get("time") or "")[:10] not in {str(x.get("time") or "")[:10] for x in merged}]
        if not older:
            break
        before = len(merged)
        merged = _merge_sorted(merged, older)
        if len(merged) > before:
            added_total += len(merged) - before
            seg_source = str(hpack.get("source") or "") or seg_source
        else:
            break
    if not added_total:
        _gapcheck_at[key] = now
        return items, None
    return merged, _resolve_source(stored_source, seg_source or "", True)


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
    """拉取 K 线。腾讯优先、东财其次、同花顺最后兜底(未登录跳过)。先查缓存，只补缺段。

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

    # 日期区间查询：优先复用磁盘全量缓存，命中则内存切片返回；
    # 未覆盖才远程整段拉 + 短 TTL。
    if beg_s or end_s:
        cache_key = f"{code}:{period_key}:{fqt}:{cap}:{beg_s}:{end_s}"
        hit = _cache_get(_kline_range_cache, cache_key, force)
        if hit is not None:
            return hit
        lo = (beg_s[:4] + "-" + beg_s[4:6] + "-" + beg_s[6:8]) if len(beg_s) >= 8 else ""
        hi = (end_s[:4] + "-" + end_s[4:6] + "-" + end_s[6:8]) if len(end_s) >= 8 else ""
        if not force:
            stored = _load_kline_disk(code, period_key, fqt)
            if stored and stored.get("items"):
                items = list(stored["items"])
                first_d = str((items[0] or {}).get("time") or "")[:10]
                last_d = str((items[-1] or {}).get("time") or "")[:10]
                # 有重叠即可复用：hi 可能是今天/未来等尚无 K 线的日期，
                # 缺的尾部由下面的 _refresh_with_tail 补（盘后已校验则直接切片）。
                if lo and hi:
                    covers = first_d <= lo and last_d >= lo
                elif lo:
                    covers = last_d >= lo
                elif hi:
                    covers = first_d <= hi
                else:
                    covers = True
                if covers:
                    live = is_cn_market_live()
                    verified_at = float(stored.get("verified_at") or 0)
                    sealed = (not live) and verified_at >= last_session_close().timestamp()
                    base = stored
                    if not sealed:
                        try:
                            base = _refresh_with_tail(
                                stored, code=code, period=period_key,
                                adjust=adjust, disk_adjust=fqt, cap=max(cap, len(items)),
                            )
                            items = list(base.get("items") or items)
                        except Exception:
                            items = list(stored["items"])
                    ranged = [it for it in items
                              if (not lo or str(it.get("time") or "")[:10] >= lo)
                              and (not hi or str(it.get("time") or "")[:10] <= hi)]
                    if ranged:
                        if cap > 0 and len(ranged) > cap:
                            ranged = ranged[-cap:]
                        result = _kline_payload({**base, "items": ranged})
                        result["full_history"] = bool(base.get("full_history"))
                        _kline_range_cache.put(cache_key, result, cached_at=now)
                        return result
        # 分段补齐：缓存缺老段时只拉 [lo, first_d) 一段，合并存盘后再切片；
        # 缺新段走尾部刷新；都不命中才整段远程。
        if not force:
            try:
                _stored2 = _load_kline_disk(code, period_key, fqt)
            except Exception:
                _stored2 = None
            if _stored2 and _stored2.get("items"):
                _items2 = list(_stored2["items"])
                _first2 = str((_items2[0] or {}).get("time") or "")[:10]
                _last2 = str((_items2[-1] or {}).get("time") or "")[:10]
                _merged2 = None
                _seg_source2 = ""
                _gap_src2 = None
                if lo and _first2 and lo < _first2:
                    from datetime import timedelta as _td
                    try:
                        _seg_end = (datetime.strptime(_first2, "%Y-%m-%d") - _td(days=1)).strftime("%Y%m%d")
                    except ValueError:
                        _seg_end = ""
                    try:
                        _seg = _fetch_remote_kline(code, period=period, adjust=adjust,
                                                  limit=cap, beg=beg_s, end=_seg_end or end_s)
                        _seg_items = [it for it in (_seg.get("items") or [])
                                      if str(it.get("time") or "")[:10] >= (lo or "")]
                        if _seg_items:
                            _have = {str(b.get("time") or "")[:10] for b in _items2}
                            _merged2 = sorted(
                                [b for b in _seg_items if str(b.get("time") or "")[:10] not in _have] + _items2,
                                key=lambda b: str(b.get("time") or ""))
                            _seg_source2 = str(_seg.get("source") or "")
                            _merged2, _gap_src2 = _backfill_middle_gaps(_merged2, code=code, period=period_key, adjust=adjust, cap=cap, stored_source=str(_stored2.get("source") or ""))
                            _merged_src2 = _gap_src2 or _resolve_source(str(_stored2.get("source") or ""), _seg_source2, True)
                            _save_kline_disk(code, period_key, fqt,
                                             {"code": code, "items": _merged2,
                                              "source": _merged_src2,
                                              "full_history": False})
                    except Exception as exc:
                        logger.info("kline segment fill %s [%s,%s): %s", code, lo, _first2, exc)
                elif hi and _last2 and hi > _last2:
                    try:
                        _base2 = _refresh_with_tail(_stored2, code=code, period=period_key,
                                                    adjust=adjust, disk_adjust=fqt,
                                                    cap=max(cap, len(_items2)))
                        if _base2.get("items"):
                            _merged2 = list(_base2["items"])
                            _stored2 = dict(_base2)
                    except Exception as exc:
                        logger.info("kline tail fill %s: %s", code, exc)
                if _merged2:
                    _ranged2 = [it for it in _merged2
                                if (not lo or str(it.get("time") or "")[:10] >= lo)
                                and (not hi or str(it.get("time") or "")[:10] <= hi)]
                    if _ranged2:
                        if cap > 0 and len(_ranged2) > cap:
                            _ranged2 = _ranged2[-cap:]
                        _base_src2 = _gap_src2 or _seg_source2 or str(_stored2.get("source") or "")
                        if isinstance(_stored2, dict) and _base_src2:
                            _stored2 = {**_stored2, "source": _base_src2}
                        _result2 = _kline_payload({**_stored2, "items": _ranged2}, source=_base_src2)
                        _result2["full_history"] = bool(_stored2.get("full_history"))
                        _kline_range_cache.put(cache_key, _result2, cached_at=now)
                        return _result2
        result = _fetch_remote_kline(
            code, period=period, adjust=adjust, limit=cap, beg=beg_s, end=end_s
        )
        if result.get("items"):
            # 纯往前翻（只有 end，没有 beg）：把这页老段拼进硬盘，以后首屏直接就是新牌子
            try:
                _disk3 = None if force else _load_kline_disk(code, period_key, fqt)
                if _disk3 and _disk3.get("items") and not beg_s and end_s:
                    _d3 = list(_disk3["items"])
                    _f3 = str((_d3[0] or {}).get("time") or "")[:10]
                    _h3 = (end_s[:4] + "-" + end_s[4:6] + "-" + end_s[6:8]) if len(end_s) >= 8 else ""
                    if _h3 and _h3 < _f3:
                        _have3 = {_bar_time(b) for b in _d3 if _bar_time(b)}
                        _new3 = [b for b in (result.get("items") or []) if _bar_time(b) and _bar_time(b) not in _have3]
                        if _new3:
                            _full3 = sorted(_new3 + _d3, key=lambda b: str(b.get("time") or ""))
                            _save_kline_disk(code, period_key, fqt,
                                             {"code": code, "items": _full3,
                                              "source": _resolve_source(str(_disk3.get("source") or ""), str(result.get("source") or ""), True),
                                              "full_history": False})
                            result = dict(result)
                            result["source"] = _resolve_source(str(_disk3.get("source") or ""), str(result.get("source") or ""), True)
            except Exception:
                pass
            _kline_range_cache.put(cache_key, result, cached_at=now)
        return result

    mem_key = f"{code}:{period_key}:{fqt}"
    if not force:
        hit = _kline_live_cache.get(mem_key)
        if hit is not None:
            return _slice_payload(hit, cap)

    stored = None if force else _load_kline_disk(code, period_key, fqt)
    live = is_cn_market_live()

    if not beg_s and not end_s and cap > _FULL_HISTORY_LIMIT and period_key in _FULL_HISTORY_PERIODS and not force:
        need_full = (not stored) or len(stored.get("items") or []) < cap or not stored.get("full_history")
        if not need_full and stored:
            verified_at = float(stored.get("verified_at") or 0)
            if (not live) and verified_at >= last_session_close().timestamp():
                result = _kline_payload(stored)
                _kline_live_cache.put(mem_key, result, cached_at=now)
                rr = dict(result)
                rr["full_history"] = True
                return _slice_payload(rr, cap)
        if need_full:
            try:
                result = _fetch_full_history(code, period=period_key, adjust=adjust, cap=cap)
                if result.get("items"):
                    _save_kline_disk(code, period_key, fqt, result)
                    _kline_live_cache.put(mem_key, result, cached_at=now)
                    return _slice_payload(result, cap)
            except Exception as exc:
                logger.info("full history failed %s: %s", code, exc)

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
    """去掉各源多出来的字段，收成对外逐笔包。最后一条即最新成交。

    ``volume`` / ``volume_lots`` 统一为手：东财 / 腾讯原生即手；
    同花顺原生为股，已在解析时换算（金额仍按股算）。
    """
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
    if result.get("pre_price") is None:
        pre = _ticks_prev_close(result.get("code") or "", result.get("day") or "")
        if pre is not None:
            result["pre_price"] = pre
    return result


_ticks_prev_close_cache: dict[str, Any] = {"at": 0.0, "map": {}}


def _ticks_prev_close(code: str, day: str) -> float | None:
    """逐笔缺昨收时用日K前一收补齐，让分时纵轴有中心锚点。

    失败返回 None（调用方保持原样）。结果按天缓存，避免每个逐笔请求都拉一次日K。
    """
    from core.fmt import to_float

    code = (code or "").strip()
    if not code:
        return None
    now = time.time()
    cache = _ticks_prev_close_cache
    if now - float(cache.get("at") or 0) > 600:
        cache["at"] = now
        cache["map"] = {}
    key = f"{code}"
    if key in cache["map"]:
        return cache["map"][key]
    try:
        pack = _fetch_remote_kline(code, period="day", adjust="none", limit=2)
    except Exception:
        return None
    items = pack.get("items") or []
    if len(items) < 2:
        return None
    pre = to_float(items[-2].get("close"))
    cache["map"][key] = pre
    return pre


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
    if int(payload.get("version") or 0) not in (1, _TICKS_DISK_VERSION):
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
        # 整日（pos=0）一律切片全拉，保证完整带子；只有明确要最近 N 笔才走 count。
        fetch_kwargs: dict[str, Any] = {} if limit == 0 else {"count": limit}
        fut = _ths_executor.submit(
            fetch_ths_time_and_sales, code, **fetch_kwargs
        )
        try:
            _, ts_items = fut.result(timeout=_THS_SOURCE_TIMEOUT)
        except FuturesTimeout:
            logger.warning("ticks ths %s 超时(>%ss)，fallback 到下一源", code, _THS_SOURCE_TIMEOUT)
            return _ticks_payload({}, source="")
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


# 非交易时间自动升级逐笔缓存到同花顺的失败退避：同 key 10 分钟内只试一次，
# 避免每次打开页面都打一次几十片的整日拉取。
_THS_TICKS_UPGRADE_TTL = 600.0
_ths_ticks_upgrade_cooldown: dict[str, float] = {}


def _upgrade_ticks_to_ths(code: str, stored: dict[str, Any]) -> dict[str, Any] | None:
    """非交易时间把上个交易日整日逐笔升级到同花顺并落盘。

    成功返回 THS 整包（调用方切片），失败返回 None（调用方继续用旧缓存）。
    整日走切片拉取（非 count 分支），保证是完整带子而不是最近 300 笔。
    """
    day = str(stored.get("day") or stored.get("session_day") or "")
    key = f"{code}:{day}"
    now = time.time()
    if now - _ths_ticks_upgrade_cooldown.get(key, 0) < _THS_TICKS_UPGRADE_TTL:
        return None
    _ths_ticks_upgrade_cooldown[key] = now
    try:
        fut = _ths_executor.submit(fetch_ths_time_and_sales, code)
        _, ts_items = fut.result(timeout=120.0)
    except Exception as exc:  # noqa: BLE001
        logger.info("tonghuashun ticks upgrade failed %s: %s", code, exc)
        return None
    rows = [r for r in ts_items or [] if isinstance(r, dict)]
    if not rows:
        return None
    rows.sort(key=lambda r: (str(r.get("time") or ""), _tick_seq(r)))
    # 跨源笔数不可比（东财是 3 秒快照约 4500 行，同花顺是真实成交），
    # 只要求 THS 带覆盖到缓存末尾：都收到收盘即视为完整可替换。
    stored_items = stored.get("items") or []
    stored_last = _ticks_time_key(
        stored.get("last_time") or (stored_items[-1].get("time") if stored_items else "")
    )
    remote_last = _ticks_time_key(rows[-1].get("time"))
    if remote_last < stored_last:
        return None
    pack = _ensure_ticks_day(_ticks_payload({"code": code, "items": rows}, source="tonghuashun"))
    logger.info("ticks ths upgrade %s: %s rows replacing %s", code, len(rows), len(stored_items))
    return _save_ticks_disk(code, pack, finalized=True)


def _fetch_remote_ticks(code: str, *, pos: int | str = 0) -> dict[str, Any]:
    """分时逐笔优先东财，其次腾讯，已登录同花顺仅作最后兜底。首个有数据的源即返回。"""
    pos_n = _normalize_ticks_pos(pos)

    try:
        pack: dict[str, Any] = _call_with_retry(
            fetch_eastmoney_ticks, code, {"pos": pos_n}, label="eastmoney ticks"
        )
    except ValueError:
        raise
    if isinstance(pack, dict) and pack.get("items"):
        return _ensure_ticks_day(_ticks_payload(pack, source="eastmoney"))

    pack = _call_with_retry(fetch_tencent_ticks, code, {"pos": pos_n}, label="tencent ticks")
    if isinstance(pack, dict) and pack.get("items"):
        return _ensure_ticks_day(_ticks_payload(pack, source="tencent"))

    if _ths_ready():
        result = _fetch_ths_ticks(code, pos=pos_n)
        if result.get("items"):
            return _ensure_ticks_day(result)

    result = _ticks_payload({}, source="")
    if not result.get("code"):
        result["code"] = code
    return _ensure_ticks_day(result)


def _json_safe_number(value: Any) -> Any:
    """把 NaN/Inf 以及 numpy 标量收成 JSON 可编码的普通类型。"""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    try:
        import math

        num = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(num):
        return None
    return num


def _sanitize_ticks_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """逐笔行做 JSON 安全清洗，避免应答序列化失败（encode 失败）。"""
    clean: list[dict[str, Any]] = []
    for row in items or []:
        if not isinstance(row, dict):
            continue
        out: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, float) or hasattr(value, "item"):
                out[key] = _json_safe_number(value)
            else:
                out[key] = value
        clean.append(out)
    return clean


def _history_ticks_from_minute_kline(code: str, iso: str) -> dict[str, Any]:
    """历史逐笔兜底：用分钟 K 合成该日分时点（price/avg_price/volume）。

    同花顺历史逐笔只保留最近一个交易日，更早的日期用分钟 K 合成：
    依次试 1m / 5m / 15m / 30m / 60m 的日期区间（走三源 fallback），
    1m 额外试最近 4000 根（覆盖腾讯约 2 天）。合成点粒度较粗，
    分时成交明细仍为空，但分时图有线可画。
    """
    digits = re.sub(r"\D", "", iso or "")
    if len(digits) < 8:
        return _empty_ticks(code, day=iso)
    day_key = f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    day_compact = digits[:8]
    pack: dict[str, Any] = {}
    bars: list[dict[str, Any]] = []
    used_period = "1m"
    for period, allow_last in (("1m", True), ("5m", False), ("15m", False), ("30m", False), ("60m", False)):
        try:
            pack = _fetch_remote_kline(
                code, period=period, adjust="none", limit=600,
                beg=day_compact, end=day_compact,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("history minute fallback %s %s %s range failed: %s", code, iso, period, exc)
            continue
        bars = [b for b in (pack.get("items") or [])
                if isinstance(b, dict) and str(b.get("time") or "")[:10] == day_key]
        if bars:
            used_period = period
            break
        if allow_last:
            try:
                pack = _fetch_remote_kline(code, period=period, adjust="none", limit=4000)
            except Exception as exc:  # noqa: BLE001
                logger.info("history minute fallback %s %s last-n failed: %s", code, iso, exc)
                continue
            bars = [b for b in (pack.get("items") or [])
                    if isinstance(b, dict) and str(b.get("time") or "")[:10] == day_key]
            if bars:
                used_period = period
                break
    if not bars:
        return _empty_ticks(code, day=iso)
    prev = pack.get("pre_price")
    try:
        day_pack = _fetch_remote_kline(code, period="day", adjust="none", limit=5)
        for i, b in enumerate(day_pack.get("items") or []):
            if str(b.get("time") or "")[:10] == day_key and i > 0:
                prev = (day_pack["items"][i - 1] or {}).get("close")
                break
    except Exception:  # noqa: BLE001
        pass
    use_amount = any(to_float(b.get("amount")) not in (None,) for b in bars)
    pv = 0.0
    shares = 0.0
    items: list[dict[str, Any]] = []
    for b in bars:
        price = to_float(b.get("close"))
        vol = to_float(b.get("volume")) or 0.0
        amt = to_float(b.get("amount"))
        if price is None:
            continue
        if use_amount and amt:
            pv += amt
            shares += vol * 100.0
        elif vol > 0:
            pv += price * vol
            shares += vol
        clock = str(b.get("time") or "")
        m = re.search(r"(\d{2}:\d{2})(?::\d{2})?", clock)
        items.append({
            "time": f"{m.group(1)}:00" if m else clock,
            "price": price,
            "volume": vol,
            "avg_price": (pv / shares) if shares else price,
            "count": None,
            "side": "",
            "side_label": "",
        })
    if not items:
        return _empty_ticks(code, day=iso)
    return {
        "code": code,
        "name": pack.get("name") or "",
        "pre_price": prev,
        "last_time": items[-1]["time"],
        "last_price": items[-1]["price"],
        "day": day_key,
        "source": f"{pack.get('source') or 'kline'}·{used_period}合成",
        "count": len(items),
        "items": items,
        "cached": False,
        "session_day": day_key,
        "cached_at": "",
        "synthetic": True,
    }


def fetch_ticks(
    code: str,
    *,
    pos: int | str = 0,
    force: bool = False,
    day: str = "",
) -> dict[str, Any]:
    """拉取成交明细。已登录同花顺优先，未登录先东财、腾讯兜底。

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
        iso = want_day.isoformat()
        stored = _load_ticks_disk(code, want_day)
        if stored:
            return _slice_ticks_pos(stored, pos_n)
        out = _empty_ticks(code, day=iso)
        out["error"] = f"{iso} 暂无逐笔缓存（历史日只读缓存，不再拉取同花顺）"
        return out

    live = is_cn_session_open()
    # 当天：force（前端刷新行情）时跳过磁盘缓存，重新拉远程并覆盖当天文件；
    # 历史日已在上面只读返回，不受 force 影响。
    stored = None if force else _load_ticks_disk(code)

    if stored and not live:
        # 盘后固定缓存：直接读文件，不再补远程、不再升级同花顺。
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
