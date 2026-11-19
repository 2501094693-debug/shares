"""MACD：数据接入 + 主入口。

日线统一走 ``company.line.fetcher.fetch_kline``（默认前复权）。
为让区间起点附近的 EMA / DEA 尽量收敛，拉取时自动向前多取暖机数据。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.codes import normalize_code

from company.analysis.line.MACD.core import (
    DEFAULT_FAST,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
    compute_macd,
)


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


def _fetch_day_range(
    code: str,
    *,
    beg_iso: str,
    end_iso: str,
    adjust: str = "qfq",
    warmup_days: int = 120,
) -> dict[str, Any]:
    """拉日线：覆盖 [beg, end]，并向前多取暖机数据。"""
    from company.line.fetcher import fetch_kline

    pad = (
        datetime.strptime(beg_iso, "%Y-%m-%d") - timedelta(days=int(warmup_days))
    ).strftime("%Y%m%d")
    end_compact = end_iso.replace("-", "")

    pack = fetch_kline(
        code,
        period="day",
        adjust=adjust,
        beg=pad,
        end=end_compact,
        limit=10000,
    )
    items = list(pack.get("items") or [])
    source = str(pack.get("source") or "")
    name = str(pack.get("name") or "")

    # 若最早一根仍晚于 beg（缺暖机），继续往前翻页
    need_before = (
        datetime.strptime(beg_iso, "%Y-%m-%d") - timedelta(days=int(warmup_days))
    ).strftime("%Y-%m-%d")
    for _ in range(40):
        if not items:
            break
        first = _bar_date(items[0])
        if not first or first <= need_before:
            break
        if pack.get("full_history"):
            break
        try:
            cur_end = (
                datetime.strptime(first, "%Y-%m-%d") - timedelta(days=1)
            ).strftime("%Y%m%d")
        except ValueError:
            break
        older = fetch_kline(
            code,
            period="day",
            adjust=adjust,
            end=cur_end,
            limit=2000,
        )
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
        pack = older
        if older.get("full_history"):
            break

    items.sort(key=_bar_date)
    return {
        "code": str(pack.get("code") or code),
        "name": name,
        "source": source,
        "items": items,
    }


def analyze_macd(
    code: str,
    beg: str,
    end: str = "",
    *,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
    price: str = "close",
    adjust: str = "qfq",
) -> dict[str, Any]:
    """主入口：拉日线后计算 MACD（默认前复权，参数 10/22/8）。"""
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
    result = compute_macd(
        list(hist.get("items") or []),
        beg_iso,
        end_iso,
        fast=fast,
        slow=slow,
        signal=signal,
        price=price,
    )
    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        **result,
    }
