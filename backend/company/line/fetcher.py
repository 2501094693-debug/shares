"""K 线 / 逐笔的统一入口：双源 fallback + 短 TTL。

- ``fetch_kline``：腾讯优先、东财兜底。
  腾讯没有季 / 半年 / 年 / 120 分钟，这些周期会直接走东财。
- ``fetch_ticks``：东财优先、腾讯兜底。

两边返回字段不完全一样，K 线 / 逐笔会先收成同一套再给 API / 统计用。
不提供分时 trends2。区间涨跌见 ``company.statistics.period_returns``。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.cache import TtlCache
from core.codes import normalize_code
from company.line.eastmoney_kline import fetch_line as fetch_eastmoney_line
from company.line.eastmoney_ticks import fetch_ticks as fetch_eastmoney_ticks
from company.line.tencent_kline import fetch_line as fetch_tencent_line
from company.line.tencent_ticks import fetch_ticks as fetch_tencent_ticks

logger = logging.getLogger(__name__)

# K 线盘中变化慢，缓存 2 分钟；逐笔要跟上成交，只缓存 8 秒。
KLINE_TTL = 120
TICKS_TTL = 1

_kline_cache = TtlCache(KLINE_TTL)
_ticks_cache = TtlCache(TICKS_TTL)


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

    # 缓存 key 用规范化后的值，避免 2024-01-01 和 20240101 各存一份。
    period_key = (period or "day").strip().lower()
    fqt = str(adjust if adjust is not None else "qfq").strip().lower()
    cap = int(limit or 320)
    beg_s = (beg or "").replace("-", "").strip()
    end_s = (end or "").replace("-", "").strip()
    cache_key = f"{code}:{period_key}:{fqt}:{cap}:{beg_s}:{end_s}"
    now = time.time()

    hit = _cache_get(_kline_cache, cache_key, force)
    if hit is not None:
        return hit

    kwargs = {
        "period": period,
        "adjust": adjust,
        "limit": cap,
        "beg": beg_s,
        "end": end_s,
    }

    # 腾讯不支持的周期会立刻 ValueError（文案含「不支持」），不当失败、直接改走东财。
    # 其它错误（超时、空数据）也落到东财，只打日志。
    pack: dict[str, Any] = {}
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

    # 东财是兜底。入参不合法继续往外抛；网络/解析失败则返回空包，source 为空。
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
