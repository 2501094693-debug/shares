"""股性（gene）：拉日线 → MACD → 金叉事件与 DIF≥DEA 段涨跌幅。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

from company.analysis.line.MACD.core import compute_macd
from company.analysis.line.MACD.service import (
    _fetch_day_range,
    _warmup_calendar_days,
)
from company.analysis.line.gene.config import (
    DEFAULT_ADJUST,
    DEFAULT_EXTREMA_LAYERS,
    DEFAULT_EXTREMA_SERIES,
    DEFAULT_EXTREMA_SMOOTH,
    DEFAULT_NEAR_RATIO,
    DEFAULT_PRESET,
    DEFAULT_PRICE,
)
from company.analysis.line.gene.core import analyze_gene_from_macd, resolve_preset
from company.analysis.line.local_extrema.service import compute_alternating_extrema


def _iso(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 8:
        raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or bar.get("date") or "")[:10]


def _closes_by_date(bars: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for bar in bars:
        d = _bar_date(bar)
        close = to_float(bar.get("close"))
        if d and close is not None and close > 0:
            out[d] = float(close)
    return out


def _bars_in_range(
    bars: list[dict[str, Any]],
    beg_iso: str,
    end_iso: str,
) -> list[dict[str, Any]]:
    """截取 ``[beg, end]`` 内交易日，供三级峰谷序列使用。"""
    out: list[dict[str, Any]] = []
    for bar in bars:
        d = _bar_date(bar)
        if d and beg_iso <= d <= end_iso:
            out.append(bar)
    return out


def analyze_gene(
    code: str,
    beg: str,
    end: str = "",
    *,
    preset: str = DEFAULT_PRESET,
    near_ratio: float = DEFAULT_NEAR_RATIO,
    adjust: str = DEFAULT_ADJUST,
    price: str = DEFAULT_PRICE,
    extrema_layers: int = DEFAULT_EXTREMA_LAYERS,
    extrema_series: str = DEFAULT_EXTREMA_SERIES,
    extrema_smooth: int = DEFAULT_EXTREMA_SMOOTH,
) -> dict[str, Any]:
    """主入口：日线 + 指定 MACD 预设，输出区间内每个金叉日相关数据。

    ``preset``：``10,20,7`` 或 ``12,26,9``。
    另在区间日线上算 ``extrema_layers``（默认 3）级交替峰谷，给每个金叉附带
    此前最近峰/谷贴近度统计。
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    beg_iso = _iso(beg)
    end_iso = _iso(end) if str(end or "").strip() else _today_iso()
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    preset_key, fast, slow, signal = resolve_preset(preset)
    warmup = _warmup_calendar_days(slow, signal)
    hist = _fetch_day_range(
        norm,
        beg_iso=beg_iso,
        end_iso=end_iso,
        adjust=adjust,
        warmup_days=warmup,
    )
    bars = list(hist.get("items") or [])
    if not bars:
        raise ValueError("无日线数据")

    # MACD 从暖机后的最早一根算起，保证 beg 首日也能用到昨 DIF/DEA
    macd_beg = _bar_date(bars[0]) or beg_iso
    # 再往前留一天缓冲：若首根恰为 beg，至少多覆盖前一自然日附近的交易日
    if macd_beg >= beg_iso:
        macd_beg = (
            datetime.strptime(beg_iso, "%Y-%m-%d") - timedelta(days=10)
        ).strftime("%Y-%m-%d")

    macd = compute_macd(
        bars,
        macd_beg,
        end_iso,
        fast=fast,
        slow=slow,
        signal=signal,
        price=price,
    )

    layers = max(1, int(extrema_layers or DEFAULT_EXTREMA_LAYERS))
    range_bars = _bars_in_range(bars, beg_iso, end_iso)
    extrema_pack: dict[str, Any] = {}
    extrema_seq: list[dict[str, Any]] = []
    if len(range_bars) >= 3:
        extrema_pack = compute_alternating_extrema(
            range_bars,
            layers=layers,
            series=extrema_series or DEFAULT_EXTREMA_SERIES,
            smooth_window=max(1, int(extrema_smooth or DEFAULT_EXTREMA_SMOOTH)),
        )
        extrema_seq = list(extrema_pack.get("extrema") or [])

    gene = analyze_gene_from_macd(
        list(macd.get("items") or []),
        beg_iso,
        end_iso,
        near_ratio=near_ratio,
        closes_by_date=_closes_by_date(bars),
        extrema=extrema_seq,
        extrema_layers=layers,
        preset=preset_key,
        fast=fast,
        slow=slow,
        signal=signal,
    )
    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        "price": price,
        "extrema_series": extrema_pack.get("series") or extrema_series,
        "extrema_smooth": extrema_pack.get("smooth_window") or extrema_smooth,
        "extrema_peak_count": extrema_pack.get("peak_count"),
        "extrema_trough_count": extrema_pack.get("trough_count"),
        **gene,
    }
