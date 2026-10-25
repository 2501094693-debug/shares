"""个股相对基准日收盘的四价涨跌幅（波动区间）。

输入：股票代码 + 起始日期（可选结束日期）。
以「起始日期前一个交易日」的收盘价为基准，对区间内每个交易日的
开盘 / 最高 / 最低 / 收盘，分别计算相对该基准的涨跌幅；并汇总
四价在整个区间内的涨跌幅范围（最小 / 最大）。

日线数据统一走 ``company.line.fetcher.fetch_kline``（默认前复权）。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

FACTORS: tuple[str, ...] = ("open", "high", "low", "close")
FACTOR_LABELS: dict[str, str] = {
    "open": "开盘价",
    "high": "最高价",
    "low": "最低价",
    "close": "收盘价",
}


def _iso(value: str) -> str:
    """``YYYYMMDD`` / ``YYYY-MM-DD`` / ``YYYY/MM/DD`` → ``YYYY-MM-DD``。"""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 8:
        raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def _ymd(value: str) -> str:
    return _iso(value).replace("-", "")


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or "")[:10]


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _pct(price: float | None, base: float) -> float | None:
    if price is None or base == 0:
        return None
    return round(float(price) / base - 1.0, 6)


def compute_undulate(
    bars: list[dict[str, Any]],
    beg: str,
    end: str = "",
) -> dict[str, Any]:
    """在已排序的日线序列上算相对基准收盘的四价涨跌幅（纯函数，便于单测）。

    - 基准：``beg`` 之前最近一个交易日的收盘价
    - 区间：``[beg, end]`` 内交易日；``end`` 空则用序列最后一根
    """
    if not bars:
        raise ValueError("无日线数据")

    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else "9999-12-31"
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    ordered = sorted(bars, key=_bar_date)

    base_bar: dict[str, Any] | None = None
    for bar in ordered:
        d = _bar_date(bar)
        if not d:
            continue
        if d < beg_iso:
            base_bar = bar
        elif d >= beg_iso:
            break
    if base_bar is None:
        raise ValueError(f"{beg_iso} 之前无交易日，无法取基准收盘价")

    base_close = to_float(base_bar.get("close"))
    if base_close is None or base_close == 0:
        raise ValueError(f"基准日 {_bar_date(base_bar)} 收盘价无效")

    days: list[dict[str, Any]] = []
    # factor -> list of (date, pct)
    series: dict[str, list[tuple[str, float]]] = {f: [] for f in FACTORS}

    for bar in ordered:
        d = _bar_date(bar)
        if not d or d < beg_iso or d > end_iso:
            continue
        prices = {f: to_float(bar.get(f)) for f in FACTORS}
        pcts = {f: _pct(prices[f], base_close) for f in FACTORS}
        day: dict[str, Any] = {
            "date": d,
            "prices": dict(prices),
            "pct": dict(pcts),
        }
        # 中文键便于直接展示
        for f in FACTORS:
            day[FACTOR_LABELS[f]] = pcts[f]
            if pcts[f] is not None:
                series[f].append((d, float(pcts[f])))
        days.append(day)

    if not days:
        raise ValueError(f"区间 [{beg_iso}, {end_iso if end else '最新'}] 无交易日")

    used_end = days[-1]["date"]
    range_block: dict[str, Any] = {}
    for f in FACTORS:
        pts = series[f]
        if not pts:
            range_block[f] = {
                "factor": f,
                "label": FACTOR_LABELS[f],
                "min": None,
                "max": None,
                "min_date": None,
                "max_date": None,
            }
            continue
        min_date, min_v = min(pts, key=lambda x: x[1])
        max_date, max_v = max(pts, key=lambda x: x[1])
        range_block[f] = {
            "factor": f,
            "label": FACTOR_LABELS[f],
            "min": min_v,
            "max": max_v,
            "min_date": min_date,
            "max_date": max_date,
        }

    return {
        "beg": beg_iso,
        "end": used_end,
        "input_end": _iso(end) if end else None,
        "base": {
            "date": _bar_date(base_bar),
            "close": base_close,
        },
        "days": days,
        "range": range_block,
        "count": len(days),
    }


def _fetch_day_range(
    code: str,
    *,
    beg_iso: str,
    end_iso: str,
    adjust: str = "qfq",
) -> dict[str, Any]:
    """拉日线：覆盖 [beg, end]，并多取 beg 前若干根以拿到基准收盘。"""
    from company.line.fetcher import fetch_kline

    # 向前多取约 30 个自然日，确保有基准前收；不够再翻页
    pad = (
        datetime.strptime(beg_iso, "%Y-%m-%d") - timedelta(days=30)
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

    # 若最早一根仍晚于 beg（缺基准日），继续往前翻页
    for _ in range(40):
        if not items:
            break
        first = _bar_date(items[0])
        if not first or first < beg_iso:
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


def analyze_undulate(
    code: str,
    beg: str,
    end: str = "",
    *,
    adjust: str = "qfq",
) -> dict[str, Any]:
    """主入口：个股相对基准收盘的四价涨跌幅与区间范围（默认前复权）。"""
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
    result = compute_undulate(
        list(hist.get("items") or []), beg_iso, end_iso
    )

    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        **result,
    }
