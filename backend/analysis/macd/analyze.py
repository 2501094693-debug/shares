"""单股：MACD 金叉筛 → 最大稳定区间 → 收盘/最低前低分 + 股指反向日 → 综合分。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.codes import normalize_code

from analysis.macd.config import (
    DEFAULT_ADJUST,
    DEFAULT_BAND,
    DEFAULT_FACTOR,
    DEFAULT_FAST,
    DEFAULT_INDEX,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_NEAR_RATIO,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
    DEFAULT_W_DIV,
    DEFAULT_W_PRIOR,
)
from analysis.macd.score import composite_score
from analysis.macd.signals import classify_macd_cross
from company.analysis.line.evaluate.core import (
    LOW_FACTOR_CHOICES,
    TEST_FACTOR_CHOICES,
    find_max_range,
    lowest_day,
    score_low_point,
    slim_window,
)
from company.analysis.line.evaluate.service import (
    DEFAULT_LAYERS,
    DEFAULT_SMOOTH_WINDOW,
    EXTREMA_LOOKBACK_BARS,
    EXTREMA_LOOKBACK_DAYS,
    MAX_LOOKBACK_DAYS,
    PROBE_LOOKBACK_DAYS,
    _ensure_extrema_history,
    _extrema_bars,
    _safe_divergence,
)
from company.analysis.line.MACD.core import compute_macd
from company.analysis.line.undulate.service import (
    _bar_date,
    _fetch_day_range,
    _iso,
    _today_iso,
)
from company.analysis.line.undulate.volatility import _norm_index_code


def _match_score(scored: dict[str, Any] | None) -> float | None:
    if not scored:
        return None
    match = scored.get("target")
    if not isinstance(match, dict):
        match = scored.get("match")
    if not isinstance(match, dict):
        return None
    try:
        n = float(match.get("score"))
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def _score_series(
    extrema_bars: list[dict[str, Any]],
    window: dict[str, Any],
    *,
    series: str,
    layers: int,
    smooth_window: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """稳定区间内取 series 最低日并打分；返回 (low_point, score_block)。"""
    if series not in LOW_FACTOR_CHOICES:
        return None, None
    low = lowest_day(window, factor=series)
    if low is None or not extrema_bars:
        return low, None
    scored = score_low_point(
        extrema_bars,
        low["date"],
        series=series,
        layers=layers,
        smooth_window=smooth_window,
        low_price=low.get("price"),
    )
    analysis = scored.get("analysis") or {}
    block = {
        "series": scored.get("series"),
        "target": scored.get("match"),
        "layers": int(layers),
        "extrema_count": analysis.get("extrema_count"),
        "trough_count": analysis.get("trough_count"),
    }
    return low, block


def analyze_macd_stable(
    code: str,
    *,
    end: str = "",
    factor: str = DEFAULT_FACTOR,
    band: float = DEFAULT_BAND,
    index: str = DEFAULT_INDEX,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    adjust: str = DEFAULT_ADJUST,
    near_ratio: float = DEFAULT_NEAR_RATIO,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
    w_prior: float = DEFAULT_W_PRIOR,
    w_div: float = DEFAULT_W_DIV,
    layers: int = DEFAULT_LAYERS,
    smooth_window: int = DEFAULT_SMOOTH_WINDOW,
    index_hist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """主入口：MACD 四类信号筛 → 最大 ±band 区间 → 双价前低分 + 反向日综合分。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    if factor not in TEST_FACTOR_CHOICES:
        raise ValueError(f"不支持的波动口径 {factor!r}，可选 {TEST_FACTOR_CHOICES}")

    end_iso = _iso(end) if end else _today_iso()
    band_abs = abs(float(band))
    index_code = str(index or DEFAULT_INDEX).strip() or DEFAULT_INDEX
    adj = str(adjust or DEFAULT_ADJUST).strip().lower() or DEFAULT_ADJUST

    search_lb = max(60, int(lookback_days))
    probe_lb = min(search_lb, int(PROBE_LOOKBACK_DAYS))
    max_lb = max(search_lb, MAX_LOOKBACK_DAYS)

    def _pull(lb_days: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        beg_lb = (
            datetime.strptime(end_iso, "%Y-%m-%d") - timedelta(days=int(lb_days))
        ).strftime("%Y-%m-%d")
        pack = _fetch_day_range(norm, beg_iso=beg_lb, end_iso=end_iso, adjust=adj)
        items = list(pack.get("items") or [])
        if not items:
            raise ValueError("无日线数据")
        return pack, items

    hist, bars = _pull(probe_lb)
    meta = {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adj,
        "factor": factor,
        "band": band_abs,
        "index": index_code,
        "near_ratio": abs(float(near_ratio)),
        "fast": int(fast),
        "slow": int(slow),
        "signal": int(signal),
        "layers": int(layers),
        "smooth": int(smooth_window),
    }

    # --- MACD 信号（短窗即够；暖机由 bars 头部提供） ---
    bar_dates = [d for d in (_bar_date(b) for b in bars) if d]
    macd_beg = bar_dates[0] if bar_dates else end_iso
    try:
        macd_pack = compute_macd(
            bars,
            macd_beg,
            end_iso,
            fast=fast,
            slow=slow,
            signal=signal,
            price="close",
        )
    except ValueError as exc:
        return {
            **meta,
            "found": False,
            "reason": "macd_fail",
            "message": str(exc),
            "macd": None,
        }

    macd_items = list(macd_pack.get("items") or [])
    cross = classify_macd_cross(macd_items, near_ratio=near_ratio)
    macd_block = {
        "beg": macd_pack.get("beg"),
        "end": macd_pack.get("end"),
        "fast": macd_pack.get("fast"),
        "slow": macd_pack.get("slow"),
        "signal": macd_pack.get("signal"),
        "latest": macd_pack.get("latest"),
        "cross": cross,
    }
    if not cross.get("matched"):
        return {
            **meta,
            "found": False,
            "reason": "no_macd_signal",
            "message": "未命中水下/水上金叉或即将金叉",
            "macd": macd_block,
        }

    # --- 最大稳定区间 ---
    result = find_max_range(bars, end=end_iso, factor=factor, band=band_abs)
    if result.get("reached_start"):
        need_lb = max(
            search_lb,
            int(EXTREMA_LOOKBACK_DAYS),
            min(max_lb, max(probe_lb * 2, search_lb)),
        )
        while True:
            hist, bars = _pull(need_lb)
            meta["name"] = str(hist.get("name") or meta["name"])
            meta["source"] = str(hist.get("source") or meta["source"])
            result = find_max_range(bars, end=end_iso, factor=factor, band=band_abs)
            if not result.get("found"):
                break
            if result.get("reached_start") and need_lb < max_lb:
                need_lb = min(max_lb, max(need_lb * 2, need_lb + 1))
                continue
            break

    if not result.get("found"):
        return {
            **meta,
            "found": False,
            "reason": "no_stable_range",
            "message": (
                f"最新交易日单日窗口已超出 ±{band_abs * 100:.2f}% 波动带，"
                "未找到满足条件的区间"
            ),
            "macd": macd_block,
            "first_fail": slim_window(result.get("first_fail")),
        }

    window = result["window"]
    beg_iso = window["beg"]
    used_end = window["end"]

    bars, hist = _ensure_extrema_history(
        norm, bars, hist, end_iso=used_end, adjust=adj
    )
    meta["name"] = str(hist.get("name") or meta["name"])
    meta["source"] = str(hist.get("source") or meta["source"])
    extrema_bars = _extrema_bars(bars, end=used_end)

    low_close, score_close_block = _score_series(
        extrema_bars,
        window,
        series="close",
        layers=layers,
        smooth_window=smooth_window,
    )
    low_low, score_low_block = _score_series(
        extrema_bars,
        window,
        series="low",
        layers=layers,
        smooth_window=smooth_window,
    )

    resolved_index = (
        index_hist
        if isinstance(index_hist, dict) and index_hist.get("items") is not None
        else None
    )
    if resolved_index is None:
        try:
            from company.analysis.line.undulate.volatility import (
                _fetch_index_day_range,
            )

            resolved_index = _fetch_index_day_range(
                _norm_index_code(index_code) or index_code,
                beg_iso=beg_iso,
                end_iso=used_end,
            )
        except Exception:  # noqa: BLE001
            resolved_index = None

    # 偏离口径：all → close
    div_factor = factor if factor in ("open", "high", "low", "close") else "close"
    divergence = _safe_divergence(
        norm,
        index_code,
        beg=beg_iso,
        end=used_end,
        factor=div_factor,
        stock_bars=bars,
        stock_name=str(hist.get("name") or ""),
        stock_source=str(hist.get("source") or ""),
        index_hist=resolved_index,
    )

    s_close = _match_score(score_close_block)
    s_low = _match_score(score_low_block)
    rev = divergence.get("reverse_count")
    try:
        rev_i = int(rev) if rev is not None else None
    except (TypeError, ValueError):
        rev_i = None
    range_days = int(window.get("count") or 0)
    scored = composite_score(
        score_close=s_close,
        score_low=s_low,
        reverse_count=rev_i,
        range_days=range_days,
        w_prior=w_prior,
        w_div=w_div,
    )

    return {
        **meta,
        "found": True,
        "reason": "ok",
        "macd": macd_block,
        "range": {
            "beg": beg_iso,
            "end": used_end,
            "count": range_days,
            "base": window.get("base"),
            "range": window.get("range"),
        },
        "tested": result.get("tested"),
        "reached_start": result.get("reached_start"),
        "first_fail": slim_window(result.get("first_fail")),
        "low_point_close": low_close,
        "low_point_low": low_low,
        "score_close": score_close_block,
        "score_low": score_low_block,
        "divergence": divergence,
        "score": scored,
        "extrema_lookback_bars": int(EXTREMA_LOOKBACK_BARS),
    }


__all__ = ["analyze_macd_stable"]
