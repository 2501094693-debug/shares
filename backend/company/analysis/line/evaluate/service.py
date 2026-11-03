"""区间评估主入口：±band 最大波动区间 + 最低价日评分 + 股指四价走势 + 股指反向偏离分。

流程：

1. 结束日固定为最新交易日；起始日先也设为最新交易日，得到窗口
   ``[起始日, 结束日]``；
2. 用 ``undulate`` 口径（相对起始日前一交易日收盘的四价涨跌幅）判断窗口
   是否落在 ``[-band, band]``（默认 ±9%）。满足则起始日往前推一个交易日，
   继续判断，直到首次不满足，取最后一次满足的区间为「最大起始日期范围」；
3. 在该区间内找出收盘价（``low_factor`` 可切换四价）最低的交易日；
4. 用最近 ``EXTREMA_LOOKBACK_BARS`` 个交易日跑 ``local_extrema``
   （默认层级 3）得到谷序列并打分；取相对价距最小的谷，
   低点分 = 谷分 × (1 − |(最低价 − 谷价) / 谷价|)；
5. 在同一区间对个股与指数做四价波动统计，给出 S0/U/S1 走势标签
   （上行 / 下行 / 冲高回落 / 探底回升 / 横盘）；
6. 用 ``compare`` 在该区间统计股指方向相反日占比，得到偏离分
   （反向日数 / 有效日数 × 100）。

取数策略（加速）：
- 先短窗（``PROBE_LOOKBACK_DAYS``）快筛；未命中即返回，避免无谓拉长历史；
- 命中后一次拉齐搜索上限与谷序列所需历史，并视需要重搜最大区间；
- 可传入预取的 ``index_hist``，路径与偏离分复用个股/指数 bars，避免二次拉数。

个股日线走 ``company.line.fetcher.fetch_kline``（默认前复权）；
指数日线走 ``undulate.volatility``；股指方向对比走 ``compare``。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.codes import normalize_code

from company.analysis.line.compare.codes import FACTORS as COMPARE_FACTORS
from company.analysis.line.compare.service import compare_divergence
from company.analysis.line.undulate.service import (
    FACTORS as UNDULATE_FACTORS,
    _bar_date,
    _fetch_day_range,
    _iso,
    _today_iso,
)
from company.analysis.line.undulate.volatility import (
    _fetch_index_day_range,
    _norm_index_code,
    compute_volatility,
)

from company.analysis.line.evaluate.core import (
    DEFAULT_BAND,
    LOW_FACTOR_CHOICES,
    TEST_FACTOR_CHOICES,
    find_max_range,
    lowest_day,
    score_low_point,
    slim_window,
)

# 默认对比指数（上证指数），可传其它宽基公开码
DEFAULT_INDEX = "000001"
# 默认回溯自然日；若窗口触到数据头部仍满足，会自动翻倍向前扩展
DEFAULT_LOOKBACK_DAYS = 900
MAX_LOOKBACK_DAYS = 3650
# 未命中快筛：先只拉近端日线；命中后再一次拉长
PROBE_LOOKBACK_DAYS = 120
# 低点谷序列：最近 N 个交易日 + 层级 3
EXTREMA_LOOKBACK_BARS = 600
# 拉数自然日上界（按约 252 交易日/年换算并留余量，保证能盖住 600 根）
EXTREMA_LOOKBACK_DAYS = int(EXTREMA_LOOKBACK_BARS * 365 / 252) + 60
DEFAULT_LAYERS = 3
DEFAULT_SMOOTH_WINDOW = 1


def _series_factor(factor: str) -> str:
    """evaluate 波动口径 → 单序列口径；``all`` 回退 close。"""
    key = str(factor or "close").strip().lower()
    return key if key in COMPARE_FACTORS else "close"


def _divergence_factor(factor: str) -> str:
    """evaluate 波动口径 → compare 日级口径；``all`` 回退 close。"""
    return _series_factor(factor)


def _pct_series(
    window: dict[str, Any],
    *,
    factor: str,
) -> tuple[list[str], list[float]]:
    """从 ``compute_undulate`` 结果抽出 ``(dates, pcts)``。"""
    dates: list[str] = []
    pcts: list[float] = []
    for day in window.get("days") or []:
        d = str(day.get("date") or "")[:10]
        pct = (day.get("pct") or {}).get(factor)
        if not d or pct is None:
            continue
        dates.append(d)
        pcts.append(float(pct))
    return dates, pcts


def _bars_cover_from(bars: list[dict[str, Any]], beg_iso: str) -> bool:
    """日线最早日期是否已覆盖 ``beg_iso``（含）。"""
    dates = [d for d in (_bar_date(b) for b in bars) if d]
    return bool(dates) and min(dates) <= beg_iso


def _safe_divergence(
    code: str,
    index: str,
    *,
    beg: str,
    end: str,
    factor: str,
    stock_bars: list[dict[str, Any]] | None = None,
    stock_name: str = "",
    stock_source: str = "",
    index_hist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """股指偏离分；失败时降级为带 error 的空块，不影响整体结果。

    优先复用已有个股 / 指数 bars；缺指数时只补拉指数，避免个股二次 IO。
    """
    cmp_factor = _divergence_factor(factor)
    try:
        hist = index_hist if isinstance(index_hist, dict) else None
        idx_items = list(hist.get("items") or []) if hist is not None else None
        if stock_bars is not None and idx_items is None:
            index_code = _norm_index_code(index) or str(index or "").strip()
            hist = _fetch_index_day_range(index_code, beg_iso=beg, end_iso=end)
            idx_items = list(hist.get("items") or [])
        if stock_bars is not None and idx_items is not None:
            return compare_divergence(
                code,
                index,
                beg=beg,
                end=end,
                factor=cmp_factor,
                stock_bars=stock_bars,
                index_bars=idx_items,
                stock_name=stock_name,
                stock_source=stock_source,
                index_name=str((hist or {}).get("name") or ""),
                index_source=str((hist or {}).get("source") or ""),
            )
        return compare_divergence(
            code, index, beg=beg, end=end, factor=cmp_factor
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "factor": cmp_factor,
            "beg": beg,
            "end": end,
            "score": None,
            "count": 0,
            "reverse_count": 0,
            "dirs": {},
            "stock": {"code": code},
            "index": {"code": index},
            "error": str(exc),
        }


def _path_labels(vol: dict[str, Any] | None) -> dict[str, str]:
    """从 volatility.stats 抽出四价走势标签。"""
    stats = (vol or {}).get("stats") or {}
    out: dict[str, str] = {}
    for factor in UNDULATE_FACTORS:
        path = (stats.get(factor) or {}).get("path") or {}
        label = str(path.get("label") or "unknown")
        out[factor] = label
    return out


def _safe_paths(
    bars: list[dict[str, Any]],
    index: str,
    *,
    beg: str,
    end: str,
    stock_code: str = "",
    stock_name: str = "",
    index_hist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """区间内个股 / 指数四价波动走势；失败时降级为带 error 的空块。"""
    index_code = _norm_index_code(index) or str(index or "").strip()
    empty_paths = {f: "unknown" for f in UNDULATE_FACTORS}
    empty = {
        "beg": beg,
        "end": end,
        "stock": {
            "code": stock_code,
            "name": stock_name,
            "paths": dict(empty_paths),
        },
        "index": {
            "code": index_code,
            "name": "",
            "paths": dict(empty_paths),
        },
    }
    try:
        stock_vol = compute_volatility(bars, beg, end)
        hist = (
            index_hist
            if isinstance(index_hist, dict) and index_hist.get("items") is not None
            else _fetch_index_day_range(index_code, beg_iso=beg, end_iso=end)
        )
        index_vol = compute_volatility(list(hist.get("items") or []), beg, end)
        return {
            "beg": beg,
            "end": end,
            "stock": {
                "code": stock_code,
                "name": stock_name,
                "paths": _path_labels(stock_vol),
            },
            "index": {
                "code": str(hist.get("code") or index_code),
                "name": str(hist.get("name") or ""),
                "source": str(hist.get("source") or ""),
                "paths": _path_labels(index_vol),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {**empty, "error": str(exc)}


def _bars_on_or_before(
    bars: list[dict[str, Any]], end_iso: str
) -> list[dict[str, Any]]:
    """结束日（含）之前的日线，按日期升序。"""
    end_key = _iso(end_iso)
    out = [b for b in bars if (d := _bar_date(b)) and d <= end_key]
    out.sort(key=_bar_date)
    return out


def _extrema_bars(
    bars: list[dict[str, Any]],
    *,
    end: str,
    lookback_bars: int = EXTREMA_LOOKBACK_BARS,
) -> list[dict[str, Any]]:
    """截取结束日前最近 ``lookback_bars`` 个交易日，供谷序列评分。"""
    ordered = _bars_on_or_before(bars, end)
    n = max(1, int(lookback_bars))
    return ordered[-n:] if len(ordered) > n else ordered


def _bars_cover_extrema(bars: list[dict[str, Any]], end_iso: str) -> bool:
    """是否已有足够交易日覆盖谷序列回溯（或已触达上市以来全部历史）。"""
    ordered = _bars_on_or_before(bars, end_iso)
    if len(ordered) >= int(EXTREMA_LOOKBACK_BARS):
        return True
    # 根数不足但自然日跨度已盖住拉数上界 → 视为上市偏短，无需再拉
    extrema_beg = (
        datetime.strptime(_iso(end_iso), "%Y-%m-%d")
        - timedelta(days=int(EXTREMA_LOOKBACK_DAYS))
    ).strftime("%Y-%m-%d")
    return _bars_cover_from(ordered, extrema_beg)


def _ensure_extrema_history(
    code: str,
    bars: list[dict[str, Any]],
    hist: dict[str, Any],
    *,
    end_iso: str,
    adjust: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """命中后补齐最近 600 个交易日所需日线，供谷序列评分；已覆盖则原样返回。"""
    if _bars_cover_extrema(bars, end_iso):
        return bars, hist
    extrema_beg = (
        datetime.strptime(_iso(end_iso), "%Y-%m-%d")
        - timedelta(days=int(EXTREMA_LOOKBACK_DAYS))
    ).strftime("%Y-%m-%d")
    longer = _fetch_day_range(
        code, beg_iso=extrema_beg, end_iso=end_iso, adjust=adjust
    )
    items = list(longer.get("items") or [])
    if not items:
        return bars, hist
    if not longer.get("name") and hist.get("name"):
        longer = {**longer, "name": hist.get("name")}
    if not longer.get("source") and hist.get("source"):
        longer = {**longer, "source": hist.get("source")}
    return items, longer


def analyze_evaluate(
    code: str,
    *,
    end: str = "",
    factor: str = "close",
    low_factor: str = "close",
    band: float = DEFAULT_BAND,
    index: str = DEFAULT_INDEX,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    adjust: str = "qfq",
    layers: int = DEFAULT_LAYERS,
    smooth_window: int = DEFAULT_SMOOTH_WINDOW,
    index_hist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """主入口：最大 ±band 区间 + 最低价日评分 + 股指四价走势 + 股指偏离分。

    低点谷序列在最近 ``EXTREMA_LOOKBACK_BARS`` 个交易日上以 ``layers``（默认 3）打分，
    再对 ±band 区间最低价日取相对价距最近的谷做综合分。
    ``index_hist`` 为预取指数日线包（含 ``items``），批量任务可全市场复用。
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    if factor not in TEST_FACTOR_CHOICES:
        raise ValueError(
            f"不支持的波动口径 {factor!r}，可选 {TEST_FACTOR_CHOICES}"
        )
    if low_factor not in LOW_FACTOR_CHOICES:
        raise ValueError(
            f"不支持的取价口径 {low_factor!r}，可选 {LOW_FACTOR_CHOICES}"
        )

    end_iso = _iso(end) if end else _today_iso()
    band_abs = abs(float(band))
    index_code = str(index or DEFAULT_INDEX).strip() or DEFAULT_INDEX

    search_lb = max(60, int(lookback_days))
    probe_lb = min(search_lb, int(PROBE_LOOKBACK_DAYS))
    max_lb = max(search_lb, MAX_LOOKBACK_DAYS)

    def _pull(lb_days: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        beg_lb = (
            datetime.strptime(end_iso, "%Y-%m-%d") - timedelta(days=int(lb_days))
        ).strftime("%Y-%m-%d")
        pack = _fetch_day_range(norm, beg_iso=beg_lb, end_iso=end_iso, adjust=adjust)
        items = list(pack.get("items") or [])
        if not items:
            raise ValueError("无日线数据")
        return pack, items

    # 1) 短窗快筛：波动过大的票在这里就被剔除
    hist, bars = _pull(probe_lb)
    result = find_max_range(bars, end=end_iso, factor=factor, band=band_abs)

    meta = {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        "factor": factor,
        "low_factor": low_factor,
        "band": band_abs,
        "index": index_code,
        "layers": int(layers),
        "smooth": int(smooth_window),
        "extrema_lookback_bars": int(EXTREMA_LOOKBACK_BARS),
        "extrema_lookback_days": int(EXTREMA_LOOKBACK_DAYS),
    }

    if not result.get("found"):
        return {
            **meta,
            "found": False,
            "message": (
                f"最新交易日单日窗口已超出 ±{band_abs * 100:.2f}% 波动带，"
                "未找到满足条件的区间"
            ),
            "first_fail": slim_window(result.get("first_fail")),
        }

    # 2) 命中且短窗触顶：拉长历史后重搜；窗口已在短窗内定界则不再重搜
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
            "message": (
                f"最新交易日单日窗口已超出 ±{band_abs * 100:.2f}% 波动带，"
                "未找到满足条件的区间"
            ),
            "first_fail": slim_window(result.get("first_fail")),
        }

    window = result["window"]
    beg_iso = window["beg"]
    used_end = window["end"]

    # 3) 补齐最近 600 交易日供谷序列评分（短窗已定界时只多这一次长拉）
    bars, hist = _ensure_extrema_history(
        norm, bars, hist, end_iso=used_end, adjust=adjust
    )
    meta["name"] = str(hist.get("name") or meta["name"])
    meta["source"] = str(hist.get("source") or meta["source"])

    low = lowest_day(window, factor=low_factor)
    extrema_bars = _extrema_bars(bars, end=used_end)

    score_block: dict[str, Any] | None = None
    if low is not None and extrema_bars:
        scored = score_low_point(
            extrema_bars,
            low["date"],
            series=low_factor,
            layers=layers,
            smooth_window=smooth_window,
            low_price=low.get("price"),
        )
        analysis = scored.get("analysis") or {}
        score_block = {
            "series": scored.get("series"),
            "target": scored.get("match"),
            "layers": int(layers),
            "extrema_beg": _bar_date(extrema_bars[0]) if extrema_bars else None,
            "extrema_end": _bar_date(extrema_bars[-1]) if extrema_bars else None,
            "extrema_count": analysis.get("extrema_count"),
            "peak_count": analysis.get("peak_count"),
            "trough_count": analysis.get("trough_count"),
            "peak_scores": analysis.get("peak_scores"),
            "trough_scores": analysis.get("trough_scores"),
        }

    resolved_index = (
        index_hist
        if isinstance(index_hist, dict) and index_hist.get("items") is not None
        else None
    )
    if resolved_index is None:
        try:
            resolved_index = _fetch_index_day_range(
                index_code, beg_iso=beg_iso, end_iso=used_end
            )
        except Exception:  # noqa: BLE001
            resolved_index = None

    paths = _safe_paths(
        bars,
        index_code,
        beg=beg_iso,
        end=used_end,
        stock_code=norm,
        stock_name=str(hist.get("name") or ""),
        index_hist=resolved_index,
    )
    divergence = _safe_divergence(
        norm,
        index_code,
        beg=beg_iso,
        end=used_end,
        factor=factor,
        stock_bars=bars,
        stock_name=str(hist.get("name") or ""),
        stock_source=str(hist.get("source") or ""),
        index_hist=resolved_index,
    )

    return {
        **meta,
        "found": True,
        "range": {
            "beg": beg_iso,
            "end": used_end,
            "count": window.get("count"),
            "base": window.get("base"),
            "range": window.get("range"),
        },
        "days": window.get("days"),
        "tested": result.get("tested"),
        "reached_start": result.get("reached_start"),
        "first_fail": slim_window(result.get("first_fail")),
        "low_point": low,
        "score": score_block,
        "paths": paths,
        "divergence": divergence,
    }
