"""聪明投机者：数据接入 + 主入口。

日线统一走 ``company.line.fetcher.fetch_kline``（默认前复权）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.codes import normalize_code

from company.analysis.line.T.core import DEFAULT_RATIO, compute_trader


def _iso(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 8:
        raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or "")[:10]


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


def analyze_trader(
    code: str,
    beg: str,
    end: str = "",
    *,
    ratio: float = DEFAULT_RATIO,
    adjust: str = "qfq",
    return_history: bool = False,
) -> dict[str, Any]:
    """主入口：模拟聪明投机者，返回期末股数与平均成本。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else _today_iso()
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    hist = _fetch_day_range(
        norm, beg_iso=beg_iso, end_iso=end_iso, adjust=adjust
    )
    result = compute_trader(
        list(hist.get("items") or []),
        beg_iso,
        end_iso,
        ratio=ratio,
        return_history=return_history,
    )
    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        **result,
    }
