"""区间四价极值位置百分比与升序排名。

给定起始日期和一只股票（可选结束日期，默认今天）：
对开盘 / 收盘 / 最高 / 最低各自在 ``[beg, end]`` 内找出最高价与最低价，
再用「现价」算其在区间内的相对位置与从小到大排名：

    (现价 − 最低价) / (最高价 − 最低价) × 100%
    rank = 1 + 区间内严格更低的交易日数（1=最低，并列取竞争名次）

「现价」默认取最新实时行情的四价（开盘 / 现价 / 最高 / 最低），
实时行情不可用时回退到区间结束日那根日K的四价。
日线数据走 ``company.line.fetcher.fetch_kline``（默认前复权）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

from company.analysis.line.extremum.service import (
    FACTOR_LABELS,
    FACTORS,
    _bar_date,
    _iso,
)


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _position_pct(end_price: float, lo: float, hi: float) -> float | None:
    """(end − min) / (max − min) × 100；极差为 0 时无法定位，返回 None。"""
    span = hi - lo
    if span == 0:
        return None
    return round((end_price - lo) / span * 100.0, 4)


def _rank_asc(end_price: float, values: list[float]) -> int:
    """从小到大排名：1=最低；并列取竞争名次（严格更小的个数 + 1）。"""
    return 1 + sum(1 for v in values if v < end_price)


def compute_position(
    bars: list[dict[str, Any]],
    beg: str,
    end: str = "",
    *,
    live_prices: dict[str, float | None] | None = None,
    live_date: str = "",
) -> dict[str, Any]:
    """在已排序日线序列上算四价极值位置与升序排名（纯函数，便于单测）。

    - 区间：``[beg, end]`` 内交易日；``end`` 空则用序列最后一根
    - 现价：优先用 ``live_prices`` 的实时四价；缺失时回退到区间结束日
    - ``rank`` / ``n``：现价在区间内从小到大的名次与区间样本数
    """
    if not bars:
        raise ValueError("无日线数据")

    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else "9999-12-31"
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    ordered = sorted(bars, key=_bar_date)
    window: list[dict[str, Any]] = []
    for bar in ordered:
        d = _bar_date(bar)
        if not d or d < beg_iso or d > end_iso:
            continue
        window.append(bar)

    if not window:
        raise ValueError(f"区间 [{beg_iso}, {end_iso if end else '最新'}] 无交易日")

    end_bar = window[-1]
    used_end = _bar_date(end_bar)
    input_end = _iso(end) if end else None

    position: dict[str, Any] = {}
    for factor in FACTORS:
        pts: list[tuple[str, float]] = []
        for bar in window:
            price = to_float(bar.get(factor))
            if price is None:
                continue
            pts.append((_bar_date(bar), float(price)))

        live_price = None
        if live_prices is not None:
            raw_live = live_prices.get(factor)
            if raw_live is not None and float(raw_live) > 0:
                live_price = float(raw_live)
        end_price = live_price if live_price is not None else to_float(end_bar.get(factor))
        price_source = "live" if live_price is not None else "bar"
        price_date = (live_date or used_end) if live_price is not None else used_end
        entry: dict[str, Any] = {
            "factor": factor,
            "label": FACTOR_LABELS[factor],
            "min": None,
            "max": None,
            "min_date": None,
            "max_date": None,
            "end_price": end_price,
            "end_date": price_date,
            "price_source": price_source,
            "pct": None,
            "rank": None,
            "n": len(pts),
        }
        if pts:
            min_date, lo = min(pts, key=lambda x: x[1])
            max_date, hi = max(pts, key=lambda x: x[1])
            entry["min"] = lo
            entry["max"] = hi
            entry["min_date"] = min_date
            entry["max_date"] = max_date
            if end_price is not None:
                ep = float(end_price)
                entry["pct"] = _position_pct(ep, lo, hi)
                entry["rank"] = _rank_asc(ep, [p for _, p in pts])
        position[factor] = entry

    used_live = bool(
        live_prices and any(
            (position.get(f) or {}).get("price_source") == "live" for f in FACTORS
        )
    )
    return {
        "beg": beg_iso,
        "end": used_end,
        "input_end": input_end,
        "snapped": bool(input_end and used_end != input_end),
        "count": len(window),
        "live": used_live,
        "quote_date": (live_date or used_end) if used_live else None,
        "position": position,
    }


def _fetch_day_range(
    code: str,
    *,
    beg_iso: str,
    end_iso: str,
    adjust: str = "qfq",
) -> dict[str, Any]:
    """拉覆盖 ``[beg, end]`` 的日线。"""
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


def _fetch_live_prices(code: str, *, adjust: str) -> tuple[dict[str, float | None], str]:
    """最新实时四价：开盘 / 现价（作收盘）/ 最高 / 最低。失败返回空。"""
    if adjust != "qfq":
        return {}, ""
    try:
        from company.statistics.quote.live.fetcher import fetch_live_quote

        quote = fetch_live_quote(code) or {}
    except Exception:  # noqa: BLE001
        return {}, ""
    prices = {
        "open": to_float(quote.get("open")),
        "close": to_float(quote.get("price")),
        "high": to_float(quote.get("high")),
        "low": to_float(quote.get("low")),
    }
    prices = {
        key: (value if value is not None and value > 0 else None)
        for key, value in prices.items()
    }
    if not any(value is not None for value in prices.values()):
        return {}, ""
    return prices, _today_iso()


def analyze_position(
    code: str,
    beg: str,
    end: str = "",
    *,
    adjust: str = "qfq",
) -> dict[str, Any]:
    """主入口：个股区间四价极值位置百分比（默认前复权）。

    现价优先用最新实时四价；实时行情缺失时回退到区间结束日。
    """
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
    live_prices, live_date = _fetch_live_prices(norm, adjust=adjust)
    result = compute_position(
        list(hist.get("items") or []),
        beg_iso,
        end_iso,
        live_prices=live_prices or None,
        live_date=live_date,
    )

    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        **result,
    }
