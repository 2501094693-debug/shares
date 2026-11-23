"""K 线 bar 解析（行业轮动等共用）。"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float


def normalize_date(value: Any) -> str:
    """YYYY-MM-DD。"""
    text = str(value or "").strip().replace("/", "-")
    if len(text) >= 10:
        return text[:10]
    compact = text.replace("-", "")
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return text


def parse_bars(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清洗 K 线，保证按时间升序，并补振幅。"""
    bars: list[dict[str, Any]] = []
    for raw in items:
        close = to_float(raw.get("close"))
        if close is None:
            continue
        high = to_float(raw.get("high"))
        low = to_float(raw.get("low"))
        open_ = to_float(raw.get("open"))
        volume = to_float(raw.get("volume"))
        pct_chg = to_float(raw.get("pct_chg"))
        amplitude = to_float(raw.get("amplitude"))
        if amplitude is None and high is not None and low is not None and close:
            amplitude = round((high - low) / close * 100, 4)
        bars.append(
            {
                "date": normalize_date(raw.get("time")),
                "open": open_,
                "close": close,
                "high": high,
                "low": low,
                "volume": volume,
                "pct_chg": pct_chg,
                "amplitude": amplitude,
            }
        )
    bars.sort(key=lambda b: b["date"])
    return bars
