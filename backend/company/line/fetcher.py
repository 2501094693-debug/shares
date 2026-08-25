"""K 线 / 逐笔的统一入口：双源 fallback + 短 TTL。

- ``fetch_kline``：日/周/月/分钟，腾讯优先、东财兜底（季/半年/年/120m 只走东财）
- ``fetch_ticks``：当日成交明细，东财优先、腾讯兜底

不提供分时 trends2。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.cache import TtlCache
from company.line.eastmoney_kline import fetch_line as fetch_eastmoney_line
from company.line.eastmoney_ticks import fetch_ticks as fetch_eastmoney_ticks
from company.line.tencent_kline import ALL_PERIODS as TENCENT_PERIODS
from company.line.tencent_kline import fetch_line as fetch_tencent_line
from company.line.tencent_ticks import fetch_ticks as fetch_tencent_ticks
from core.codes import normalize_code

logger = logging.getLogger(__name__)

KLINE_TTL = 120
TICKS_TTL = 8

_kline_cache = TtlCache(KLINE_TTL)
_ticks_cache = TtlCache(TICKS_TTL)


def _kline_payload(pack: dict[str, Any], *, source: str) -> dict[str, Any]:
    items = list(pack.get("items") or [])
    return {
        "code": pack.get("code") or "",
        "name": pack.get("name") or "",
        "period": pack.get("period") or "",
        "adjust": pack.get("adjust") or "",
        "source": source or pack.get("source") or "",
        "count": len(items),
        "items": items,
    }


def _ticks_payload(pack: dict[str, Any], *, source: str) -> dict[str, Any]:
    items = list(pack.get("items") or [])
    last = items[-1] if items else {}
    return {
        "code": pack.get("code") or "",
        "name": pack.get("name") or "",
        "pre_price": pack.get("pre_price"),
        "last_time": last.get("time") or pack.get("last_time") or "",
        "last_price": last.get("price") if last else pack.get("last_price"),
        "source": source or pack.get("source") or "",
        "count": len(items),
        "items": items,
    }


def _tencent_period_ok(period: str) -> bool:
    key = (period or "day").strip().lower()
    return key in TENCENT_PERIODS or key in {
        "d",
        "daily",
        "w",
        "weekly",
        "m",
        "monthly",
        "1",
        "1min",
        "5",
        "5min",
        "15",
        "15min",
        "30",
        "30min",
        "60",
        "60min",
        "1h",
        "hour",
        "101",
        "102",
        "103",
    }


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

    cache_key = f"{code}:{period_key}:{fqt}:{cap}:{beg_s}:{end_s}"
    now = time.time()
    if not force:
        hit = _kline_cache.get(cache_key)
        if hit is not None:
            return hit

    kwargs = {
        "period": period,
        "adjust": adjust,
        "limit": cap,
        "beg": beg_s,
        "end": end_s,
    }

    pack: dict[str, Any] = {}
    if _tencent_period_ok(period_key):
        try:
            pack = fetch_tencent_line(code, **kwargs)
            if pack.get("items"):
                result = _kline_payload(pack, source="tencent")
                _kline_cache.put(cache_key, result, cached_at=now)
                return result
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
        result["period"] = period_key
    _kline_cache.put(cache_key, result, cached_at=now)
    return result


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
    if not force:
        hit = _ticks_cache.get(cache_key)
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
