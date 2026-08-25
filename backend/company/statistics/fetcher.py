"""个股盘口编排：并行拉各源，拼成公司详情页指标。

失败时返回空 dict，由 ``company.profile.get_stock_profile`` 保留乐咕成分股字段兜底。
进程内缓存 60 秒，避免详情页刷新反复打东财/腾讯。

流程：
1. 代码规范化；缓存命中则直接返回
2. 线程池并行：实时盘口、区间涨幅、现手、F10、估值、自由流通
3. 拿到上市日后，再提交历史/52 周高低（前复权需要上市年）
4. 东财盘口自带的 52 周高低优先于自行计算值
5. 用自由流通股把换手(实)、自由流通市值算出来
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from core.cache import TtlCache
from core.fmt import fmt_list_date, fmt_pct, fmt_shares, fmt_yi_wan, to_float
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

logger = logging.getLogger(__name__)

QUOTE_TTL = 60  # 秒
_cache = TtlCache(QUOTE_TTL)


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
    if "free_float_market_cap" not in result:
        if price_raw is not None:
            result["free_float_market_cap"] = fmt_yi_wan(price_raw * free_raw, unit_yi=True)
        elif mcap_raw is not None and float_raw:
            result["free_float_market_cap"] = fmt_yi_wan(
                mcap_raw * (free_raw / float_raw), unit_yi=True
            )
    if turnover_raw is not None and float_raw:
        result["turnover_real"] = fmt_pct(turnover_raw * float_raw / free_raw)


def fetch_stock_quote(code: str, *, force: bool = False) -> dict[str, Any]:
    """拉取并规范化个股盘口指标。``force=True`` 跳过内存缓存。"""
    code = normalize_code(code)
    if not code:
        return {}

    now = time.time()
    if not force:
        hit = _cache.get(code)
        if hit is not None:
            return hit

    result: dict[str, Any] = {}
    try:
        with ThreadPoolExecutor(max_workers=7) as pool:
            fut_quote = pool.submit(fetch_realtime_quote, code)
            fut_ret = pool.submit(fetch_period_returns, code)
            fut_hand = pool.submit(fetch_current_hand, code)
            fut_f10 = pool.submit(fetch_f10_profile, code)
            fut_val = pool.submit(fetch_valuation_extra, code)
            fut_ff = pool.submit(fetch_free_float_fields, code)

            list_date = ""
            try:
                realtime = fut_quote.result()
                if realtime.source == "tencent":
                    result.update(realtime.mapped or {})
                elif realtime.source == "eastmoney" and realtime.raw:
                    result.update(map_push2(realtime.raw))
                    list_date = (
                        fmt_list_date(realtime.raw.get("f189"))
                        or result.get("list_date")
                        or ""
                    )
                if not list_date:
                    list_date = result.get("list_date") or ""
            except Exception as exc:  # noqa: BLE001
                logger.warning("push2 quote failed %s: %s", code, exc)
                try:
                    result.update(fetch_tencent_quote(code) or {})
                except Exception:  # noqa: BLE001
                    pass
                list_date = result.get("list_date") or ""

            fut_ext = pool.submit(fetch_price_extremes, code, list_date)
            official_52 = {
                key: result[key] for key in ("high_52w", "low_52w") if result.get(key)
            }

            for fut, label in (
                (fut_ret, "period returns"),
                (fut_hand, "current hand"),
                (fut_f10, "f10"),
                (fut_val, "valuation"),
                (fut_ff, "free float"),
                (fut_ext, "price extremes"),
            ):
                try:
                    result.update(fut.result() or {})
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s failed %s: %s", label, code, exc)

            if official_52:
                result.update(official_52)
    except Exception as exc:  # noqa: BLE001
        logger.warning("quote fetch failed %s: %s", code, exc)
        return {}

    _apply_free_float(result)
    for key in list(result.keys()):
        if key.startswith("_"):
            result.pop(key, None)

    if result:
        _cache.put(code, result, cached_at=now)
    return result
