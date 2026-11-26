"""MACDP：数据接入 + 主入口。

日线优先东财、其次同花顺（二者带成交额）；不用腾讯盘口缓存。
为让区间起点附近的量加权 EMA / DEA 尽量收敛，拉取时自动向前多取暖机数据。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime, timedelta
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

from company.analysis.line.MACDP.core import (
    DEFAULT_FAST,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
    compute_macdp,
)

logger = logging.getLogger(__name__)

# 东财/同花顺可能阻塞或连不上；限时后换源，最后才退回通用日线缓存
_EM_TIMEOUT = 20.0
_THS_TIMEOUT = 25.0
_src_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="macdp-src")


def _iso(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 8:
        raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or "")[:10]


def _warmup_calendar_days(slow: int, signal: int) -> int:
    """暖机交易日约 slow+signal，再按交易日≈自然日×1.6 并加缓冲。"""
    bars_needed = int(slow) + int(signal) + 40
    return max(90, int(bars_needed * 1.6) + 20)


def _amount_coverage(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    ok = 0
    for bar in items:
        amt = to_float(bar.get("amount"))
        if amt is not None and amt > 0:
            ok += 1
    return ok / len(items)


def _slice_range(
    items: list[dict[str, Any]],
    *,
    lo: str = "",
    hi: str = "",
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for bar in items:
        d = _bar_date(bar)
        if not d:
            continue
        if lo and d < lo:
            continue
        if hi and d > hi:
            continue
        out.append(bar)
    return out


def _fetch_eastmoney(
    code: str,
    *,
    adjust: str,
    beg: str = "",
    end: str = "",
    limit: int = 10000,
) -> dict[str, Any]:
    from company.line.eastmoney.kline import fetch_line

    fut = _src_executor.submit(
        fetch_line,
        code,
        period="day",
        adjust=adjust,
        beg=beg,
        end=end,
        limit=limit,
    )
    try:
        pack = fut.result(timeout=_EM_TIMEOUT)
    except FuturesTimeout:
        logger.warning("MACDP eastmoney kline 超时(>%ss) %s", _EM_TIMEOUT, code)
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.info("MACDP eastmoney kline failed %s: %s", code, exc)
        return {}
    if not isinstance(pack, dict):
        return {}
    pack = dict(pack)
    pack["source"] = "eastmoney"
    return pack


def _fetch_tonghuashun(
    code: str,
    *,
    adjust: str,
    beg: str = "",
    end: str = "",
    limit: int = 10000,
) -> dict[str, Any]:
    from company.line.tonghuashun.kline import fetch_line

    fut = _src_executor.submit(
        fetch_line,
        code,
        period="day",
        adjust=adjust,
        beg=beg,
        end=end,
        limit=limit,
    )
    try:
        pack = fut.result(timeout=_THS_TIMEOUT)
    except FuturesTimeout:
        logger.warning("MACDP ths kline 超时(>%ss) %s", _THS_TIMEOUT, code)
        return {}
    except Exception as exc:  # noqa: BLE001
        logger.info("MACDP ths kline failed %s: %s", code, exc)
        return {}
    if not isinstance(pack, dict):
        return {}
    pack = dict(pack)
    pack["source"] = str(pack.get("source") or "tonghuashun")
    return pack


def _fetch_fetcher_fallback(
    code: str,
    *,
    adjust: str,
    beg: str = "",
    end: str = "",
    limit: int = 10000,
) -> dict[str, Any]:
    """通用日线兜底（可能无成交额；core 会退回典型价）。"""
    from company.line.fetcher import fetch_kline

    pack = fetch_kline(
        code,
        period="day",
        adjust=adjust,
        beg=beg,
        end=end,
        limit=limit,
    )
    if not isinstance(pack, dict):
        return {}
    pack = dict(pack)
    src = str(pack.get("source") or "cache")
    pack["source"] = f"{src}·fallback"
    return pack


def _fetch_amount_pack(
    code: str,
    *,
    adjust: str,
    beg: str = "",
    end: str = "",
    limit: int = 10000,
) -> dict[str, Any]:
    """东财 → 同花顺（须成交额过半）；都失败再退回通用日线。"""
    errors: list[str] = []
    for label, func in (
        ("eastmoney", _fetch_eastmoney),
        ("tonghuashun", _fetch_tonghuashun),
    ):
        try:
            pack = func(code, adjust=adjust, beg=beg, end=end, limit=limit)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")
            logger.info("MACDP %s kline failed %s: %s", label, code, exc)
            continue
        items = list(pack.get("items") or [])
        if not items:
            errors.append(f"{label}: empty")
            continue
        cov = _amount_coverage(items)
        if cov < 0.5:
            errors.append(f"{label}: amount_coverage={cov:.0%}")
            logger.info(
                "MACDP %s kline amount thin %s (%.0f%%)，换源",
                label,
                code,
                cov * 100,
            )
            continue
        pack["source"] = str(pack.get("source") or label)
        return pack

    logger.warning(
        "MACDP 东财/同花顺均无成交额日线 %s，退回通用缓存：%s",
        code,
        "; ".join(errors) if errors else "无可用源",
    )
    pack = _fetch_fetcher_fallback(
        code, adjust=adjust, beg=beg, end=end, limit=limit
    )
    if pack.get("items"):
        return pack
    detail = "; ".join(errors) if errors else "无可用源"
    raise ValueError(f"MACDP 无法取得日线（东财/同花顺/缓存）：{detail}")


def _extend_older(
    code: str,
    *,
    items: list[dict[str, Any]],
    source: str,
    name: str,
    adjust: str,
    need_before: str,
) -> tuple[list[dict[str, Any]], str, str]:
    """若最早一根仍晚于暖机起点，继续往前翻页。

    已是 fallback 源时不再反复打东财/同花顺，直接用通用日线翻页。
    """
    use_fallback_only = "fallback" in str(source or "")
    for _ in range(40):
        if not items:
            break
        first = _bar_date(items[0])
        if not first or first <= need_before:
            break
        try:
            cur_end = (
                datetime.strptime(first, "%Y-%m-%d") - timedelta(days=1)
            ).strftime("%Y%m%d")
        except ValueError:
            break
        try:
            if use_fallback_only:
                older = _fetch_fetcher_fallback(
                    code, adjust=adjust, end=cur_end, limit=2000
                )
            else:
                older = _fetch_amount_pack(
                    code,
                    adjust=adjust,
                    end=cur_end,
                    limit=2000,
                )
                if "fallback" in str(older.get("source") or ""):
                    use_fallback_only = True
        except ValueError:
            break
        older_items = [
            b
            for b in (older.get("items") or [])
            if _bar_date(b) and _bar_date(b) < first
        ]
        if not older_items:
            break
        have = {_bar_date(b) for b in items if _bar_date(b)}
        fresh = [b for b in older_items if _bar_date(b) not in have]
        items = fresh + items
        if older.get("source"):
            source = str(older.get("source") or source)
        if older.get("name") and not name:
            name = str(older.get("name") or "")
        if older.get("full_history"):
            break
    return items, source, name


def _fetch_day_range(
    code: str,
    *,
    beg_iso: str,
    end_iso: str,
    adjust: str = "qfq",
    warmup_days: int = 120,
) -> dict[str, Any]:
    """拉日线（东财/同花顺）：覆盖 [beg, end]，并向前多取暖机数据。"""
    pad = (
        datetime.strptime(beg_iso, "%Y-%m-%d") - timedelta(days=int(warmup_days))
    ).strftime("%Y%m%d")
    end_compact = end_iso.replace("-", "")
    need_before = (
        datetime.strptime(beg_iso, "%Y-%m-%d") - timedelta(days=int(warmup_days))
    ).strftime("%Y-%m-%d")

    pack = _fetch_amount_pack(
        code,
        adjust=adjust,
        beg=pad,
        end=end_compact,
        limit=10000,
    )
    items = _slice_range(
        list(pack.get("items") or []),
        lo=need_before,
        hi=end_iso,
    )
    source = str(pack.get("source") or "")
    name = str(pack.get("name") or "")

    items, source, name = _extend_older(
        code,
        items=items,
        source=source,
        name=name,
        adjust=adjust,
        need_before=need_before,
    )

    items.sort(key=_bar_date)
    return {
        "code": str(pack.get("code") or code),
        "name": name,
        "source": source,
        "items": items,
    }


def analyze_macdp(
    code: str,
    beg: str,
    end: str = "",
    *,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
    adjust: str = "qfq",
) -> dict[str, Any]:
    """主入口：东财/同花顺日线后计算 MACDP（默认前复权，参数 10/20/7）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else _today_iso()
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    warmup = _warmup_calendar_days(slow, signal)
    hist = _fetch_day_range(
        norm,
        beg_iso=beg_iso,
        end_iso=end_iso,
        adjust=adjust,
        warmup_days=warmup,
    )
    result = compute_macdp(
        list(hist.get("items") or []),
        beg_iso,
        end_iso,
        fast=fast,
        slow=slow,
        signal=signal,
    )
    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        **result,
    }
