"""筹码 V2 HTTP 路由（双池 + 分时分价）。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.analysis.line.chip.core import MAX_BINS, MIN_BINS
from company.analysis.line.chip.v2_core import (
    DEFAULT_DECAY_MODE,
    DECAY_MODES,
    normalize_decay_mode,
)
from company.analysis.line.chip.v2_service import (
    chip_v2_meta,
    run_symbol_v2,
    to_payload_v2,
)

router = APIRouter()

_MODE_HINT = "|".join(DECAY_MODES)
_MODE_ALIASES = {
    "even",
    "avg",
    "均匀",
    "平均",
    "profit_first",
    "获利",
    "获利优先",
    "cut_first",
    "loss",
    "割肉",
    "割肉优先",
}


def _parse_mode(value: str) -> str:
    """校验衰减模式；空 / auto 取默认。"""
    raw = str(value or "").strip().lower()
    if not raw or raw == "auto":
        return DEFAULT_DECAY_MODE
    if raw not in DECAY_MODES and raw not in _MODE_ALIASES:
        raise ValueError(f"decay_mode 须为 {_MODE_HINT}")
    return normalize_decay_mode(raw)


@router.get("/api/stocks/line-chip-v2/meta")
def stocks_line_chip_v2_meta():
    """双池分时筹码口径说明。"""
    return ok(chip_v2_meta())


@router.get("/api/stocks/line-chip-v2")
def stocks_line_chip_v2(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD（必填）"),
    end: str = Query("", description="截止日期，默认今天"),
    bins: int = Query(200, description=f"价格分箱数 {MIN_BINS}~{MAX_BINS}"),
    decay_mode: str = Query(DEFAULT_DECAY_MODE, description=f"衰减模式 {_MODE_HINT}"),
    source: str = Query("auto", description="日线 auto|ths|fallback"),
):
    """[beg, end] 双池筹码：已知池分布 + unknown_shares。"""
    if not code:
        return err("缺少参数 code", 400)
    if not str(beg or "").strip():
        return err("缺少参数 beg", 400)
    if bins < MIN_BINS or bins > MAX_BINS:
        return err(f"bins 须在 {MIN_BINS}~{MAX_BINS} 之间", 400)
    try:
        mode = _parse_mode(decay_mode)
    except ValueError as exc:
        return err(str(exc), 400)
    try:
        out = run_symbol_v2(
            code,
            beg=beg,
            end=end,
            bins=bins,
            decay_mode=mode,
            source=source,
        )
        return ok(to_payload_v2(out))
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/line-chip-v2/snapshot")
def stocks_line_chip_v2_snapshot(
    code: str = Query("", description="股票代码，如 600519"),
    beg: str = Query(..., description="起始日期 YYYY-MM-DD（必填）"),
    end: str = Query("", description="快照截止日，默认今天"),
    bins: int = Query(200, description=f"价格分箱数 {MIN_BINS}~{MAX_BINS}"),
    decay_mode: str = Query(DEFAULT_DECAY_MODE, description=f"衰减模式 {_MODE_HINT}"),
    source: str = Query("auto", description="日线 auto|ths|fallback"),
):
    """窗口末日已知池快照（不含逐日 series）。"""
    if not code:
        return err("缺少参数 code", 400)
    if not str(beg or "").strip():
        return err("缺少参数 beg", 400)
    if bins < MIN_BINS or bins > MAX_BINS:
        return err(f"bins 须在 {MIN_BINS}~{MAX_BINS} 之间", 400)
    try:
        mode = _parse_mode(decay_mode)
    except ValueError as exc:
        return err(str(exc), 400)
    try:
        out = run_symbol_v2(
            code,
            beg=beg,
            end=end,
            bins=bins,
            decay_mode=mode,
            source=source,
            with_history=False,
        )
        payload = to_payload_v2(out)
        payload.pop("series", None)
        return ok(payload)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
