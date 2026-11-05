"""日线段划分服务：拉日线后调用 ``compute_sections``。

日线数据统一走 ``company.line.fetcher.fetch_kline``（默认前复权）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.codes import normalize_code

from company.analysis.line.prior_low import _bar_date, _iso
from company.analysis.line.section.core import compute_sections


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _fetch_day_range(
    code: str,
    *,
    beg_iso: str,
    end_iso: str,
    adjust: str = "qfq",
) -> dict[str, Any]:
    from company.line.fetcher import fetch_kline

    pack = fetch_kline(
        code,
        period="day",
        adjust=adjust,
        beg=beg_iso.replace("-", ""),
        end=end_iso.replace("-", ""),
        limit=10000,
    )
    items = list(pack.get("items") or [])
    items.sort(key=_bar_date)
    return {
        "code": str(pack.get("code") or code),
        "name": str(pack.get("name") or ""),
        "source": str(pack.get("source") or ""),
        "items": items,
    }


def analyze_sections(
    code: str,
    beg: str,
    end: str = "",
    *,
    series: str = "close",
    band_pct: float = 0.09,
    min_runs: int = 2,
    adjust: str = "qfq",
) -> dict[str, Any]:
    """主入口：把某只股票区间日线划分为涨 / 跌 / 横盘段（含子段）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else _today_iso()
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    hist = _fetch_day_range(norm, beg_iso=beg_iso, end_iso=end_iso, adjust=adjust)
    items = list(hist.get("items") or [])
    if not items:
        raise ValueError("无日线数据")

    result = compute_sections(
        items,
        series=series,
        band_pct=band_pct,
        min_runs=min_runs,
    )

    used_end = _bar_date(items[-1])
    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        "beg": beg_iso,
        "end": used_end,
        "input_end": end_iso,
        "snapped": (end_iso != used_end) if end else False,
        "count": len(items),
        **result,
    }
