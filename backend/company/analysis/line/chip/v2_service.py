"""筹码 V2 服务：自由流通股 + 窗口日线 + 分时分价双池推演。"""

from __future__ import annotations

import logging
from concurrent.futures import as_completed
from typing import Any

import numpy as np

from company.analysis.line.chip.core import DEFAULT_BINS, MAX_BINS, MIN_BINS
from company.analysis.line.chip.service import load_daily
from company.analysis.line.chip.v2_core import (
    DEFAULT_DECAY_MODE,
    DECAY_MODES,
    normalize_decay_mode,
    run_chip_v2,
)
from company.line.session import cn_now
from company.line.tonghuashun import intraday as ths_intraday
from core.codes import normalize_code
from core.fmt import to_float

logger = logging.getLogger(__name__)

_STAT_KEYS = (
    "close",
    "profit_ratio",
    "avg_cost",
    "median",
    "cost70_low",
    "cost70_high",
    "cost90_low",
    "cost90_high",
    "concentration70",
    "concentration90",
    "peak",
)


def _digits(value: Any) -> str:
    import re

    return re.sub(r"\D", "", str(value or ""))[:8]


def _iso(digits: str) -> str:
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return ""


def _today() -> str:
    return cn_now().strftime("%Y-%m-%d")


def _resolve_day(value: Any) -> str:
    return _iso(_digits(value)) or ""


def free_float_shares(code: str) -> float:
    """自由流通股（股）；取不到直接报错。"""
    from company.statistics.quote.fetch.free_float import calc as free_float_calc

    data = free_float_calc(code) or {}
    raw = data.get("free_float_shares")
    if raw is None:
        raise ValueError(f"{code} 取不到自由流通股")
    try:
        shares = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{code} 自由流通股无效") from exc
    if not np.isfinite(shares) or shares <= 0:
        raise ValueError(f"{code} 自由流通股须 > 0")
    return shares


def _fetch_trends(
    code: str,
    days: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """并发拉窗口内每日分时；任一日为空则报错。"""
    if not days:
        return {}
    fetched: dict[str, tuple[list[dict[str, Any]], str]] = {}
    futures = {
        ths_intraday._TREND_EXECUTOR.submit(ths_intraday._fetch_day_cached, code, iso): iso
        for iso in days
    }
    for future in as_completed(futures):
        iso = futures[future]
        try:
            fetched[iso] = future.result()
        except Exception as exc:  # noqa: BLE001
            logger.info("chip v2 trend failed %s %s: %s", code, iso, exc)
            fetched[iso] = ([], str(exc))

    out: dict[str, list[dict[str, Any]]] = {}
    missing: list[str] = []
    for iso in days:
        rows, error = fetched.get(iso) or ([], "")
        if not rows:
            missing.append(f"{iso}" + (f"（{error}）" if error else ""))
            continue
        out[iso] = rows
    if missing:
        raise ValueError("缺少分时成交: " + ", ".join(missing))
    return out


def _round(value: Any, digits: int = 6) -> float | None:
    number = to_float(value)
    if number is None:
        return None
    return round(float(number), digits)


def _history_row(row: dict[str, Any], digits: int = 6) -> dict[str, Any]:
    out: dict[str, Any] = {
        "date": str(row.get("date") or ""),
        "turnover": _round(row.get("turnover"), 4),
        "volume": _round(row.get("volume"), 2),
        "volume_from_unknown": _round(row.get("volume_from_unknown"), 2),
        "volume_from_known": _round(row.get("volume_from_known"), 2),
        "unknown_shares": _round(row.get("unknown_shares"), 2),
        "known_shares": _round(row.get("known_shares"), 2),
    }
    for key in ("close", "low", "high"):
        out[key] = _round(row.get(key), digits)
    for key in _STAT_KEYS:
        if key == "close":
            continue
        out[key] = _round(row.get(key), digits)
    return out


def _stats_payload(stats: dict[str, Any], digits: int = 6) -> dict[str, Any]:
    out = {key: _round(stats.get(key), digits) for key in _STAT_KEYS}
    out["date"] = str(stats.get("date") or "")
    out["turnover"] = _round(stats.get("turnover"), 4)
    out["unknown_shares"] = _round(stats.get("unknown_shares"), 2)
    out["known_shares"] = _round(stats.get("known_shares"), 2)
    return out


def run_symbol_v2(
    code: str,
    *,
    beg: str,
    end: str = "",
    bins: int = DEFAULT_BINS,
    decay_mode: str = DEFAULT_DECAY_MODE,
    source: str = "auto",
    with_history: bool = True,
) -> dict[str, Any]:
    """在 ``[beg, end]`` 上跑双池筹码；必须指定起始日。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    beg_iso = _resolve_day(beg)
    if not beg_iso:
        raise ValueError("缺少起始日 beg")
    end_iso = _resolve_day(end) or _today()
    if beg_iso > end_iso:
        raise ValueError("beg 不能晚于 end")
    mode = normalize_decay_mode(decay_mode)
    if mode not in DECAY_MODES:
        raise ValueError(f"decay_mode 须为 {'|'.join(DECAY_MODES)}")

    float_n = free_float_shares(norm)
    pack = load_daily(norm, end=end_iso, source=source)
    rows = [
        row
        for row in pack["items"]
        if beg_iso <= str(row.get("date") or "") <= end_iso
    ]
    if not rows:
        raise ValueError(f"{norm} 在 {beg_iso}~{end_iso} 无日线")

    days = [str(row["date"]) for row in rows]
    day_trends = _fetch_trends(norm, days)
    out = run_chip_v2(
        rows,
        day_trends,
        float_shares=float_n,
        bins=bins,
        decay_mode=mode,
        with_history=with_history,
    )
    out.update(
        symbol=norm,
        name=str(pack.get("name") or ""),
        source=str(pack.get("source") or ""),
        adjust="none",
        beg=beg_iso,
        end=end_iso,
        start=beg_iso,
        decay_mode=mode,
    )
    return out


def to_payload_v2(out: dict[str, Any]) -> dict[str, Any]:
    """前端 JSON：只画已知池 K；附带 unknown_shares。"""
    centers = np.asarray(out.get("centers"), dtype=float).ravel()
    chips = np.asarray(out.get("chips"), dtype=float).ravel()
    chips_share = np.asarray(out.get("chips_share"), dtype=float).ravel()
    if chips_share.size != chips.size:
        total = float(chips.sum())
        chips_share = chips / total if total > 0 else chips
    stats = out.get("stats") or {}
    history = list(out.get("history") or [])

    peaks = [
        {
            "price": _round(item.get("price"), 6),
            "weight": _round(item.get("weight"), 8),
            "cum": _round(item.get("cum"), 8),
        }
        for item in (out.get("peaks") or [])
        if isinstance(item, dict)
    ]

    return {
        "symbol": out.get("symbol"),
        "name": out.get("name") or "",
        "source": out.get("source") or "",
        "adjust": out.get("adjust") or "none",
        "beg": out.get("beg") or "",
        "end": out.get("end") or "",
        "date": str(stats.get("date") or ""),
        "start": out.get("start") or out.get("beg") or "",
        "close": _round(stats.get("close"), 6),
        "grid": [round(float(x), 6) for x in centers.tolist()],
        "chips": [round(float(x), 8) for x in chips_share.tolist()],
        "chips_shares": [round(float(x), 2) for x in chips.tolist()],
        "float_shares": _round(out.get("float_shares"), 2),
        "unknown_shares": _round(out.get("unknown_shares"), 2),
        "known_shares": _round(out.get("known_shares"), 2),
        "stats": _stats_payload(stats),
        "peaks": peaks,
        "series": [_history_row(row) for row in history],
        "meta": {
            "bins": int(len(centers)),
            "decay_mode": str(out.get("decay_mode") or DEFAULT_DECAY_MODE),
            "inject": "intraday",
            "pool": "dual",
            "rows": int(out.get("rows") or 0),
            "series": len(history),
            "unit": "chips=share(0~1), chips_shares=股, unknown_shares=股",
        },
    }


def chip_v2_meta() -> dict[str, Any]:
    """V2 口径说明。"""
    return {
        "model": {
            "pool": "dual",
            "unknown": "beg 前筹码，形状未知，只记剩余股数；初始=自由流通股",
            "known": "beg 起由分时分钟价量落入网格构建",
            "daily": (
                "分时得 new(合计 V) → V_u=V×U/(U+K)、V_k=V×K/(U+K) "
                "→ U-=V_u → K 按 decay_mode 扣 V_k → K+=new"
            ),
            "display": "只画已知池 K，另返回 unknown_shares",
            "decay_modes": {
                "uniform": "已知池各价位按存量比例扣",
                "profit": "先扣成本<收盘（获利），不够再扣亏损侧，再扣中性",
                "cut": "先扣成本>收盘（割肉），不够再扣获利侧，再扣中性",
            },
            "bins": DEFAULT_BINS,
            "decay_mode_default": DEFAULT_DECAY_MODE,
        },
        "params": {
            "code": "股票代码",
            "beg": "起始日（必填）YYYY-MM-DD",
            "end": "截止日，默认今天",
            "bins": f"价格分箱数 {MIN_BINS}~{MAX_BINS}，默认 {DEFAULT_BINS}",
            "decay_mode": "|".join(DECAY_MODES),
            "source": "日线数据源 auto|ths|fallback",
        },
        "fields": {
            "grid": "价格轴（元）",
            "chips": "已知池各价位占比（合计 1）",
            "chips_shares": "已知池各价位绝对股数",
            "unknown_shares": "未知池剩余股数",
            "known_shares": "已知池合计股数",
            "float_shares": "自由流通股",
        },
    }
