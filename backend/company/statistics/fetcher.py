"""个股盘口编排：并行拉各源，拼成公司详情页指标。

失败时返回空 dict，由 ``company.profile.get_stock_profile`` 保留乐咕成分股字段兜底。

缓存：
- 完整盘口进程内 60 秒；盘中实时每秒拉一次源站，休市用磁盘
- 磁盘按代码存一份完整盘口。休市且已是收盘快照则直接用；
  盘中只补实时价量，写回同一份磁盘；F10、自由流通、历史高低等慢变字段
  按缺失或超过 ``SLOW_TTL`` 再拉

流程：
1. 代码规范化；内存命中则直接返回
2. 磁盘可复用则直接返回；否则按需全量或增量拉取
3. 线程池并行：实时盘口、区间涨幅、现手，必要时再加 F10、估值、自由流通
4. 拿到上市日后，再提交历史/52 周高低（前复权需要上市年）
5. 东财盘口自带的 52 周高低优先于自行计算值
6. 用自由流通股把换手(实)、自由流通市值算出来
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from core.cache import TtlCache
from core.fmt import fmt_list_date, fmt_pct, fmt_price, fmt_shares, fmt_yi_wan, to_float
from company.line.session import last_session_close, market_phase, today_lunch_start
from company.statistics.sources import (
    fetch_current_hand,
    fetch_f10_profile,
    fetch_free_float_fields,
    fetch_period_returns,
    fetch_price_extremes,
    fetch_realtime_quote,
    fetch_tencent_quote,
    fetch_valuation_extra,
    map_push2,
)
from core.codes import normalize_code
from core.paths import QUOTE_CACHE_DIR, ensure_cache_dirs

logger = logging.getLogger(__name__)

QUOTE_TTL = 60  # 秒，进程内完整盘口
LIVE_QUOTE_TTL = 1  # 休市短缓存；盘中实时每秒拉源站，不走这段 TTL
SLOW_TTL = 7 * 24 * 60 * 60  # F10 / 自由流通 / 历史高低 / 额外估值
_QUOTE_DISK_VERSION = 1

_cache = TtlCache(QUOTE_TTL)
_live_cache = TtlCache(LIVE_QUOTE_TTL)
_quote_disk_lock = threading.Lock()

QuotePlan = Literal["hit", "overlay", "full"]


def _apply_free_float(result: dict[str, Any]) -> None:
    """用自由流通股补自由流通市值、换手(实)。就地改 ``result``。"""
    free_raw = to_float(result.pop("_free_float_shares_raw", None))
    float_raw = to_float(result.pop("_float_shares_raw", None)) or to_float(
        result.pop("_float_shares_push_raw", None)
    )
    price_raw = to_float(result.pop("_price_raw", None))
    turnover_raw = to_float(result.pop("_turnover_raw", None))
    mcap_raw = to_float(result.pop("_mcap_raw", None))

    if not (free_raw and free_raw > 0):
        return
    if "free_float_shares" not in result:
        result["free_float_shares"] = fmt_shares(free_raw)
    if price_raw is not None:
        result["free_float_market_cap"] = fmt_yi_wan(price_raw * free_raw, unit_yi=True)
    elif "free_float_market_cap" not in result and mcap_raw is not None and float_raw:
        result["free_float_market_cap"] = fmt_yi_wan(
            mcap_raw * (free_raw / float_raw), unit_yi=True
        )
    if turnover_raw is not None and float_raw:
        result["turnover_real"] = fmt_pct(turnover_raw * float_raw / free_raw)


def _strip_private(result: dict[str, Any]) -> dict[str, Any]:
    for key in list(result.keys()):
        if key.startswith("_"):
            result.pop(key, None)
    return result


def _meta_from_result(result: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for key, dest in (
        ("_free_float_shares_raw", "free_float_shares_raw"),
        ("_float_shares_raw", "float_shares_raw"),
        ("_float_shares_push_raw", "float_shares_raw"),
    ):
        value = to_float(result.get(key))
        if value is not None and dest not in meta:
            meta[dest] = value
    return meta


def _inject_meta(result: dict[str, Any], meta: dict[str, Any] | None) -> None:
    if not meta:
        return
    free_raw = to_float(meta.get("free_float_shares_raw"))
    if free_raw is not None and "_free_float_shares_raw" not in result:
        result["_free_float_shares_raw"] = free_raw
    float_raw = to_float(meta.get("float_shares_raw"))
    if float_raw is not None and "_float_shares_raw" not in result:
        result["_float_shares_raw"] = float_raw


def _bump_extremes(result: dict[str, Any]) -> None:
    """当日高低若突破缓存里的历史高低，就地改，免再拉全年日 K。"""
    high = to_float(result.get("high"))
    low = to_float(result.get("low"))
    high_all = to_float(result.get("high_all"))
    low_all = to_float(result.get("low_all"))
    if high is not None and (high_all is None or high > high_all):
        result["high_all"] = fmt_price(high)
    if low is not None and low > 0 and (low_all is None or low < low_all):
        result["low_all"] = fmt_price(low)


def _disk_key_part(value: str, fallback: str) -> str:
    return re.sub(r"[^\w.-]+", "_", (value or "").strip()) or fallback


def _quote_disk_path(code: str):
    ensure_cache_dirs()
    return QUOTE_CACHE_DIR / f"{_disk_key_part(code, 'unknown')}.json"


def _load_quote_disk(code: str) -> dict[str, Any] | None:
    path = _quote_disk_path(code)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(payload.get("version") or 0) != _QUOTE_DISK_VERSION:
        return None
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        return None
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    cached_at = float(payload.get("cached_at") or 0)
    return {
        "data": dict(data),
        "meta": dict(meta),
        "cached_at": cached_at,
        "slow_at": float(payload.get("slow_at") or cached_at),
    }


def _save_quote_disk(
    code: str,
    data: dict[str, Any],
    meta: dict[str, Any],
    *,
    cached_at: float,
    slow_at: float,
) -> None:
    if not data:
        return
    body = {
        "version": _QUOTE_DISK_VERSION,
        "cached_at": cached_at,
        "verified_at": time.time(),
        "slow_at": slow_at,
        "meta": meta,
        "data": dict(data),
    }
    path = _quote_disk_path(code)
    with _quote_disk_lock:
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def _need_slow(stored: dict[str, Any] | None) -> bool:
    if not stored:
        return True
    data = stored.get("data") or {}
    if not data.get("high_all") or not data.get("low_all"):
        return True
    age = time.time() - float(stored.get("slow_at") or stored.get("cached_at") or 0)
    return age > SLOW_TTL


def _quote_plan(stored: dict[str, Any] | None, force: bool) -> QuotePlan:
    if force or not stored or not stored.get("data"):
        return "full"
    phase = market_phase()
    cached_at = float(stored.get("cached_at") or 0)
    if phase == "live":
        return "overlay"
    if phase == "lunch":
        lunch = today_lunch_start()
        if lunch is not None and cached_at >= lunch.timestamp():
            return "hit"
        return "overlay"
    if cached_at >= last_session_close().timestamp():
        return "hit"
    return "overlay"


def _load_realtime(code: str) -> tuple[dict[str, Any], str]:
    """实时盘口字段 + 上市日。失败返回空 dict。"""
    try:
        realtime = fetch_realtime_quote(code)
        if realtime.source == "tencent":
            mapped = dict(realtime.mapped or {})
            return mapped, str(mapped.get("list_date") or "")
        if realtime.source == "eastmoney" and realtime.raw:
            mapped = map_push2(realtime.raw)
            list_date = (
                fmt_list_date(realtime.raw.get("f189"))
                or mapped.get("list_date")
                or ""
            )
            return mapped, str(list_date)
    except Exception as exc:  # noqa: BLE001
        logger.warning("push2 quote failed %s: %s", code, exc)
        try:
            mapped = fetch_tencent_quote(code) or {}
            return mapped, str(mapped.get("list_date") or "")
        except Exception:  # noqa: BLE001
            pass
    return {}, ""


def _fetch_remote_quote(
    code: str,
    *,
    include_slow: bool,
    seed: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    result: dict[str, Any] = dict(seed or {})
    next_meta = dict(meta or {})
    fresh = False
    try:
        workers = 7 if include_slow else 3
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fut_quote = pool.submit(_load_realtime, code)
            fut_ret = pool.submit(fetch_period_returns, code)
            fut_hand = pool.submit(fetch_current_hand, code)
            fut_f10 = pool.submit(fetch_f10_profile, code) if include_slow else None
            fut_val = pool.submit(fetch_valuation_extra, code) if include_slow else None
            fut_ff = pool.submit(fetch_free_float_fields, code) if include_slow else None

            list_date = str(result.get("list_date") or "")
            try:
                overlay, quote_list_date = fut_quote.result()
                if overlay:
                    result.update(overlay)
                    fresh = True
                list_date = quote_list_date or list_date
            except Exception as exc:  # noqa: BLE001
                logger.warning("push2 quote failed %s: %s", code, exc)

            fut_ext = (
                pool.submit(fetch_price_extremes, code, list_date)
                if include_slow
                else None
            )
            official_52 = {
                key: result[key] for key in ("high_52w", "low_52w") if result.get(key)
            }

            parts: list[tuple[Any, str]] = [
                (fut_ret, "period returns"),
                (fut_hand, "current hand"),
            ]
            if fut_f10 is not None:
                parts.append((fut_f10, "f10"))
            if fut_val is not None:
                parts.append((fut_val, "valuation"))
            if fut_ff is not None:
                parts.append((fut_ff, "free float"))
            if fut_ext is not None:
                parts.append((fut_ext, "price extremes"))

            for fut, label in parts:
                try:
                    result.update(fut.result() or {})
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s failed %s: %s", label, code, exc)

            if official_52:
                result.update(official_52)
    except Exception as exc:  # noqa: BLE001
        logger.warning("quote fetch failed %s: %s", code, exc)
        if seed:
            return dict(seed), next_meta, False
        return {}, next_meta, False

    pulled_meta = _meta_from_result(result)
    next_meta = {**next_meta, **pulled_meta}
    _inject_meta(result, next_meta)
    _apply_free_float(result)
    _bump_extremes(result)
    _strip_private(result)
    return result, next_meta, fresh


def fetch_stock_quote(code: str, *, force: bool = False) -> dict[str, Any]:
    """拉取并规范化个股盘口指标。``force=True`` 跳过内存和磁盘缓存。"""
    code = normalize_code(code)
    if not code:
        return {}

    now = time.time()
    if not force:
        hit = _cache.get(code)
        if hit is not None:
            return hit

    stored = None if force else _load_quote_disk(code)
    plan = _quote_plan(stored, force)

    if plan == "hit" and stored:
        result = dict(stored["data"])
        _publish_quote(code, result, cached_at=now)
        return result

    include_slow = plan == "full" or _need_slow(stored)
    seed = dict(stored["data"]) if stored and stored.get("data") else None
    meta = dict(stored["meta"]) if stored and stored.get("meta") else {}

    result, meta, fresh = _fetch_remote_quote(
        code,
        include_slow=include_slow,
        seed=seed,
        meta=meta,
    )
    if not result and stored and stored.get("data"):
        result = dict(stored["data"])
        _publish_quote(code, result, cached_at=now)
        return result

    if result:
        public = dict(result)
        if plan == "full" or fresh:
            prev_slow = float((stored or {}).get("slow_at") or 0)
            slow_at = now if include_slow else prev_slow or now
            _save_quote_disk(code, public, meta, cached_at=now, slow_at=slow_at)
        _publish_quote(code, public, cached_at=now)
        return public
    return {}


def _publish_quote(code: str, result: dict[str, Any], *, cached_at: float) -> None:
    """完整盘口与实时盘口共用同一份结果，避免轮询把慢变字段冲掉。"""
    _cache.put(code, result, cached_at=cached_at)
    _live_cache.put(code, result, cached_at=cached_at)


def _merge_live_fields(
    seed: dict[str, Any],
    overlay: dict[str, Any],
    meta: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = dict(seed)
    result.update(overlay)
    pulled = _meta_from_result(result)
    next_meta = {**meta, **pulled}
    _inject_meta(result, next_meta)
    _apply_free_float(result)
    _bump_extremes(result)
    _strip_private(result)
    return result, next_meta


def fetch_live_quote(code: str, *, force: bool = False) -> dict[str, Any]:
    """盘中轮询：补实时价量，叠到磁盘里的完整盘口上。

    交易时段每秒拉一次源站；休市直接用磁盘快照，不拉网。
    """
    code = normalize_code(code)
    if not code:
        return {}

    now = time.time()
    phase = market_phase()
    if phase != "live":
        hit = _live_cache.get(code)
        if hit is not None:
            return hit

    stored = _load_quote_disk(code)

    if phase != "live" and not force:
        if stored and stored.get("data"):
            result = dict(stored["data"])
            _publish_quote(code, result, cached_at=now)
            return result
        full = _cache.get(code)
        if full is not None:
            _live_cache.put(code, full, cached_at=now)
            return full

    overlay, _ = _load_realtime(code)
    if not overlay:
        if stored and stored.get("data"):
            result = dict(stored["data"])
            _publish_quote(code, result, cached_at=now)
            return result
        logger.warning("live quote failed %s: empty realtime", code)
        return {}

    seed = dict(stored["data"]) if stored and stored.get("data") else {}
    meta = dict(stored["meta"]) if stored and stored.get("meta") else {}
    result, meta = _merge_live_fields(seed, overlay, meta)
    if not result:
        return {}

    slow_at = float((stored or {}).get("slow_at") or now)
    _save_quote_disk(code, result, meta, cached_at=now, slow_at=slow_at)
    _publish_quote(code, result, cached_at=now)
    return result
