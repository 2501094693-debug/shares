"""筹码分布 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.chip.calibrate import DEFAULT_DECAYS, TARGET_KEYS, calibrate
from company.analysis.line.chip.core import DEFAULT_PEAK, MAX_BINS, MIN_BINS, PEAK_MODES
from company.analysis.line.chip.service import chip_meta, run_symbol, to_payload

router = APIRouter()

_PEAK_HINT = "|".join(PEAK_MODES)


def _peak(value: str) -> str:
    """校验三角峰口径参数；空值取默认。"""
    key = str(value or "").strip().lower()
    if not key or key == "auto":
        return DEFAULT_PEAK
    if key not in PEAK_MODES:
        raise ValueError(f"peak 须为 {_PEAK_HINT}")
    return key


def _decays(value: str) -> list[float]:
    """解析 ``decay`` 候选串（逗号分隔）；空则用内置网格。"""
    if not str(value or "").strip():
        return []
    out: list[float] = []
    for chunk in str(value).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            number = float(chunk)
        except ValueError as exc:
            raise ValueError(f"decay 候选 {chunk!r} 不是数字") from exc
        if number <= 0 or number > 5:
            raise ValueError("decay 候选须在 (0, 5] 之间")
        out.append(number)
    return out


def _peaks(value: str) -> list[str]:
    """解析 ``peaks`` 候选串（逗号分隔）；空则用全部口径。"""
    if not str(value or "").strip():
        return []
    return [_peak(chunk) for chunk in str(value).split(",")]


@router.get("/api/stocks/line-chip/meta")
def stocks_line_chip_meta():
    """同花顺手机端日线筹码分布的口径、字段与参数说明。"""
    return ok(chip_meta())


@router.get("/api/stocks/line-chip")
def stocks_line_chip(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query("", description="起始日期 YYYY-MM-DD 或 YYYYMMDD；空=最近 series_limit 个交易日"),
    end: str = Query("", description="截止日期，默认今天"),
    bins: int = Query(200, description=f"价格分箱数 {MIN_BINS}~{MAX_BINS}"),
    decay: float = Query(1.0, description="换手衰减系数，同花顺口径 1.0"),
    peak: str = Query(DEFAULT_PEAK, description=f"三角峰口径 {_PEAK_HINT}，默认成交均价"),
    source: str = Query("auto", description="auto=同花顺手机端日线优先 / ths 强制 / fallback 三源兜底"),
    series_limit: int = Query(250, description="beg 为空时返回的每日统计条数上限"),
):
    """截至 end 的筹码分布（价格轴 + 筹码量）及区间内每日获利比例/成本区间。"""
    if not code:
        return err("缺少参数 code", 400)
    if bins < MIN_BINS or bins > MAX_BINS:
        return err(f"bins 须在 {MIN_BINS}~{MAX_BINS} 之间", 400)
    if decay <= 0 or decay > 5:
        return err("decay 须在 (0, 5] 之间", 400)
    try:
        peak_key = _peak(peak)
    except ValueError as exc:
        return err(str(exc), 400)
    try:
        out = run_symbol(
            code,
            beg=beg,
            end=end,
            bins=bins,
            decay=decay,
            peak=peak_key,
            source=source,
        )
        return ok(
            to_payload(
                out,
                beg=beg,
                end=out.get("end") or end,
                series_limit=series_limit,
            )
        )
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/line-chip/snapshot")
def stocks_line_chip_snapshot(
    code: str = Query("", description="股票代码，如 600519"),
    date: str = Query("", description="筹码快照日期 YYYY-MM-DD，空=最新交易日"),
    bins: int = Query(200, description=f"价格分箱数 {MIN_BINS}~{MAX_BINS}"),
    decay: float = Query(1.0, description="换手衰减系数，同花顺口径 1.0"),
    peak: str = Query(DEFAULT_PEAK, description=f"三角峰口径 {_PEAK_HINT}，默认成交均价"),
    source: str = Query("auto", description="auto / ths / fallback"),
):
    """单个交易日的筹码分布快照（前端拖动日线时按日取筹码峰）。"""
    if not code:
        return err("缺少参数 code", 400)
    if bins < MIN_BINS or bins > MAX_BINS:
        return err(f"bins 须在 {MIN_BINS}~{MAX_BINS} 之间", 400)
    if decay <= 0 or decay > 5:
        return err("decay 须在 (0, 5] 之间", 400)
    try:
        peak_key = _peak(peak)
    except ValueError as exc:
        return err(str(exc), 400)
    try:
        out = run_symbol(
            code,
            end=date,
            bins=bins,
            decay=decay,
            peak=peak_key,
            source=source,
            with_history=False,
        )
        payload = to_payload(out, end=out.get("end") or date, series_limit=1)
        payload.pop("series", None)
        return ok(payload)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/line-chip/calibrate")
def stocks_line_chip_calibrate(
    code: str = Query("", description="股票代码，如 001216"),
    end: str = Query("", description="截止日期 YYYY-MM-DD，空=今天"),
    bins: int = Query(800, description=f"价格分箱数 {MIN_BINS}~{MAX_BINS}"),
    source: str = Query("auto", description="auto / ths / fallback"),
    decays: str = Query("", description=f"逗号分隔的衰减系数候选，空=内置网格 {DEFAULT_DECAYS}"),
    peaks: str = Query("", description=f"逗号分隔的峰值口径候选，空=全部 {_PEAK_HINT}"),
    top: int = Query(8, description="返回的候选组合条数"),
    avg_cost: float | None = Query(None, description="同花顺显示的平均成本（元）"),
    profit_ratio: float | None = Query(None, description="同花顺显示的获利比例（0~1 或百分数）"),
    median: float | None = Query(None, description="同花顺显示的中位成本（元）"),
    peak: float | None = Query(None, description="同花顺显示的筹码峰价格（元）"),
    cost70_low: float | None = Query(None, description="70% 成本区间下沿（元）"),
    cost70_high: float | None = Query(None, description="70% 成本区间上沿（元）"),
    cost90_low: float | None = Query(None, description="90% 成本区间下沿（元）"),
    cost90_high: float | None = Query(None, description="90% 成本区间上沿（元）"),
    concentration70: float | None = Query(None, description="70% 集中度（0~1 或百分数）"),
    concentration90: float | None = Query(None, description="90% 集中度（0~1 或百分数）"),
):
    """按同花顺客户端读数反解 decay 与 peak，返回误差最小的参数组合。"""
    if not code:
        return err("缺少参数 code", 400)
    if bins < MIN_BINS or bins > MAX_BINS:
        return err(f"bins 须在 {MIN_BINS}~{MAX_BINS} 之间", 400)
    goal = {
        "avg_cost": avg_cost,
        "profit_ratio": profit_ratio,
        "median": median,
        "peak": peak,
        "cost70_low": cost70_low,
        "cost70_high": cost70_high,
        "cost90_low": cost90_low,
        "cost90_high": cost90_high,
        "concentration70": concentration70,
        "concentration90": concentration90,
    }
    if all(value is None for value in goal.values()):
        return err("至少给一个基准读数：" + " / ".join(TARGET_KEYS), 400)
    try:
        out = calibrate(
            code,
            end=end,
            targets=goal,
            decays=_decays(decays) or None,
            peaks=_peaks(peaks) or None,
            bins=bins,
            source=source,
            top=top,
        )
        return ok(out)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
