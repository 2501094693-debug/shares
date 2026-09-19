"""K 线清洗：前复权认趋势，不复权认关键点。"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float


def normalize_date(value: Any) -> str:
    text = str(value or "").strip().replace("/", "-")
    if len(text) >= 10:
        return text[:10]
    compact = text.replace("-", "")
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return text


def parse_bars(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """清洗日 K，按日期升序，补振幅。"""
    bars: list[dict[str, Any]] = []
    for raw in items or []:
        close = to_float(raw.get("close"))
        if close is None:
            continue
        high = to_float(raw.get("high"))
        low = to_float(raw.get("low"))
        open_ = to_float(raw.get("open"))
        volume = to_float(raw.get("volume"))
        amount = to_float(raw.get("amount"))
        pct_chg = to_float(raw.get("pct_chg"))
        amplitude = to_float(raw.get("amplitude"))
        if amplitude is None and high is not None and low is not None and close:
            amplitude = round((high - low) / close * 100, 4)
        bars.append(
            {
                "date": normalize_date(raw.get("time") or raw.get("date")),
                "open": open_ if open_ is not None else close,
                "close": close,
                "high": high if high is not None else close,
                "low": low if low is not None else close,
                "volume": volume,
                "amount": amount,
                "pct_chg": pct_chg,
                "amplitude": amplitude,
            }
        )
    bars.sort(key=lambda b: b["date"])
    dedup: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bar in bars:
        day = bar["date"]
        if not day or day in seen:
            continue
        seen.add(day)
        dedup.append(bar)
    return dedup


def align_by_date(
    qfq: list[dict[str, Any]],
    raw: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """两列日 K 按日期对齐。缺不复权时用前复权顶上。"""
    if not qfq:
        return [], []
    raw_map = {b["date"]: b for b in (raw or []) if b.get("date")}
    aligned_raw: list[dict[str, Any]] = []
    for bar in qfq:
        hit = raw_map.get(bar["date"])
        aligned_raw.append(dict(hit) if hit else dict(bar))
    return qfq, aligned_raw


def period_return(bars: list[dict[str, Any]], days: int) -> float | None:
    """近 N 个交易日收盘涨跌幅（%）。根数不够返回 None。"""
    closes = [b["close"] for b in bars if b.get("close")]
    if days <= 0 or len(closes) <= days:
        return None
    base = closes[-(days + 1)]
    last = closes[-1]
    if not base:
        return None
    return round((last / base - 1.0) * 100.0, 3)


def mean_volume(bars: list[dict[str, Any]], days: int) -> float | None:
    if days <= 0 or not bars:
        return None
    window = bars[-days:]
    vols = [b["volume"] for b in window if b.get("volume") and b["volume"] > 0]
    if not vols:
        return None
    return sum(vols) / len(vols)


def mean_amount(bars: list[dict[str, Any]], days: int) -> float | None:
    if days <= 0 or not bars:
        return None
    window = bars[-days:]
    vals = [b["amount"] for b in window if b.get("amount") and b["amount"] > 0]
    if not vals:
        return None
    return sum(vals) / len(vals)
