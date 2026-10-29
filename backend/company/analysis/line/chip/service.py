"""筹码分布服务：同花顺手机端日线接口取数 + 本地 CYQ 推演。

取数优先级：
1. ``ths.fetch_daily``：同花顺手机端日线的 quotebridge 接口（免登录，自带换手率）；
2. 失败时回退 ``company.line.fetcher.fetch_kline``（腾讯 / 东财 / 已登录同花顺），
   换手率缺失再用流通股本由成交量补算。

筹码口径与同花顺手机端一致：首日铺满全部流通筹码，之后按换手率衰减 +
当日三角分布注入；因此返回的是「截至 end 的筹码分布」以及每日的
获利比例 / 平均成本 / 成本区间 / 集中度 / 筹码峰序列。
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

import numpy as np

from company.analysis.line.chip import ths
from company.analysis.line.chip.core import (
    DEFAULT_BINS,
    DEFAULT_DECAY,
    DEFAULT_PEAK,
    MAX_BINS,
    MIN_BINS,
    PEAK_MODES,
    normalize_peak,
    run_chip,
)
from company.line.fetcher import fetch_kline
from company.line.session import cn_now
from core.codes import normalize_code
from core.fmt import to_float

logger = logging.getLogger(__name__)

_FLOAT_TTL = 24 * 3600.0
_float_lock = threading.Lock()
_float_cache: dict[str, tuple[float, float | None]] = {}

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
    return re.sub(r"\D", "", str(value or ""))[:8]


def _iso(digits: str) -> str:
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return ""


def _today() -> str:
    return cn_now().strftime("%Y-%m-%d")


def _resolve_day(value: Any) -> str:
    return _iso(_digits(value)) or ""


def _float_shares(code: str) -> float | None:
    """流通股（股）；用于把成交量换算成换手率，取不到返回 None。

    换手率口径是「成交量 / 流通股本」；``free_float_shares`` 是自由流通股本
    （剔除大股东），拿它算会把换手率放大数倍，只在流通股本缺失时兜底。
    """
    key = code
    now = time.time()
    with _float_lock:
        hit = _float_cache.get(key)
        if hit and now - hit[0] < _FLOAT_TTL:
            return hit[1]
    shares: float | None = None
    try:
        from company.statistics.quote.fetch.free_float import calc as free_float_calc

        data = free_float_calc(code) or {}
        raw = (
            data.get("float_shares")
            or data.get("total_shares")
            or data.get("free_float_shares")
        )
        if raw:
            shares = float(raw)
    except Exception as exc:  # noqa: BLE001
        logger.info("chip float shares %s failed: %s", code, exc)
    with _float_lock:
        _float_cache[key] = (now, shares)
    return shares


def _fill_turnover(rows: list[dict[str, Any]], code: str) -> None:
    """换手率缺失时用「成交量(股) / 流通股 × 100」补；补不上就留空。"""
    missing = sum(1 for row in rows if row.get("turnover") is None)
    if not missing:
        return
    shares = _float_shares(code)
    if not shares or shares <= 0:
        return
    for row in rows:
        if row.get("turnover") is None and row.get("volume"):
            row["turnover"] = row["volume"] / shares * 100.0


def _fallback_daily(code: str) -> dict[str, Any]:
    """三源 K 线兜底：拉全历史不复权日线，成交量统一换算成股。"""
    # 传 beg 才走全历史分支；不传会被 fetcher 收成最近 500 根，筹码起点错位。
    pack = fetch_kline(code, period="day", adjust="none", limit=10000, beg="19900101")
    rows: list[dict[str, Any]] = []
    for item in pack.get("items") or []:
        if not isinstance(item, dict):
            continue
        date = str(item.get("time") or "").strip()[:10]
        if not date:
            continue
        close = to_float(item.get("close"))
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        open_ = to_float(item.get("open"))
        if close is None or high is None or low is None:
            continue
        # fetcher 统一为手；引擎按股计算换手
        volume = (to_float(item.get("volume")) or 0.0) * 100.0
        rows.append({
            "date": date,
            "open": open_ if open_ is not None else close,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            # 成交额（元）；有值才能按成交均价定位三角峰，缺则退回 (O+H+L+C)/4
            "amount": to_float(item.get("amount")),
            "turnover": to_float(item.get("turnover")),
        })
    rows.sort(key=lambda r: r["date"])
    if not rows:
        raise ValueError(f"{code} 取不到日线")
    return {
        "code": code,
        "sec": code,
        "name": str(pack.get("name") or ""),
        "start": rows[0]["date"],
        "total": len(rows),
        "items": rows,
        "source": str(pack.get("source") or "fallback"),
    }


def load_daily(
    code: str,
    *,
    end: str = "",
    source: str = "auto",
) -> dict[str, Any]:
    """按 ``source`` 取日线；``auto`` 先同花顺手机端，失败再走三源兜底。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    end_iso = _resolve_day(end) or _today()
    prefer = (source or "auto").strip().lower()

    if prefer in ("auto", "ths", "tonghuashun"):
        try:
            pack = ths.fetch_daily(norm, end=end_iso)
            _fill_turnover(pack["items"], norm)
            return pack
        except Exception as exc:  # noqa: BLE001
            if prefer != "auto":
                raise
            logger.info("ths chip daily %s failed, fallback: %s", norm, exc)

    if prefer in ("auto", "fallback", "kline"):
        pack = _fallback_daily(norm)
        _fill_turnover(pack["items"], norm)
        return pack

    raise ValueError(f"未知数据源 source={source!r}（可选 auto|ths|fallback）")


def _round(value: Any, digits: int = 6) -> float | None:
    number = to_float(value)
    if number is None:
        return None
    return round(float(number), digits)


def _history_row(row: dict[str, Any], digits: int = 6) -> dict[str, Any]:
    out: dict[str, Any] = {
        "date": str(row.get("date") or ""),
        "turnover": _round(row.get("turnover"), 4),
    }
    for key in ("close", "low", "high"):
        out[key] = _round(row.get(key), digits)
    for key in _STAT_KEYS:
        if key in ("close",):
            continue
        out[key] = _round(row.get(key), digits)
    return out


def _stats_payload(stats: dict[str, Any], digits: int = 6) -> dict[str, Any]:
    out = {key: _round(stats.get(key), digits) for key in _STAT_KEYS}
    out["date"] = str(stats.get("date") or "")
    out["turnover"] = _round(stats.get("turnover"), 4)
    return out


def run_symbol(
    code: str,
    *,
    beg: str = "",
    end: str = "",
    bins: int = DEFAULT_BINS,
    decay: float = DEFAULT_DECAY,
    peak: str = DEFAULT_PEAK,
    source: str = "auto",
    with_history: bool = True,
) -> dict[str, Any]:
    """计算截至 ``end`` 的筹码分布，并给出 ``[beg, end]`` 的每日序列。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    end_iso = _resolve_day(end) or _today()
    beg_iso = _resolve_day(beg)
    peak_key = normalize_peak(peak)

    pack = load_daily(norm, end=end_iso, source=source)
    rows = [row for row in pack["items"] if row["date"] <= end_iso]
    if not rows:
        raise ValueError(f"{norm} 在 {end_iso} 之前无日线")
    # 筹码需要从上市以来累积，先取全历史再截断展示区间
    out = run_chip(
        rows,
        bins=bins,
        decay=decay,
        peak=peak_key,
        with_history=with_history,
    )
    out.update(
        symbol=norm,
        name=str(pack.get("name") or ""),
        source=str(pack.get("source") or ""),
        adjust="none",
        beg=beg_iso or str((out["history"][0] or {}).get("date") if out["history"] else ""),
        end=end_iso,
        start=str(pack.get("start") or ""),
        decay=decay,
        peak=peak_key,
    )
    return out


def to_payload(
    out: dict[str, Any],
    *,
    beg: str = "",
    end: str = "",
    series_limit: int = 250,
) -> dict[str, Any]:
    """把 ndarray / numpy 标量收成前端可直插图表的 JSON。"""
    centers = np.asarray(out.get("centers"), dtype=float).ravel()
    chips = np.asarray(out.get("chips"), dtype=float).ravel()
    stats = out.get("stats") or {}
    history = list(out.get("history") or [])

    beg_iso = _resolve_day(beg)
    if beg_iso:
        history = [row for row in history if str(row.get("date") or "") >= beg_iso]
    limit = int(series_limit or 0)
    if limit > 0 and len(history) > limit and not beg_iso:
        history = history[-limit:]

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
        "beg": beg_iso or str(history[0].get("date") if history else ""),
        "end": _resolve_day(end) or out.get("end") or "",
        "date": str(stats.get("date") or ""),
        "start": out.get("start") or "",
        "close": _round(stats.get("close"), 6),
        "grid": [round(float(x), 6) for x in centers.tolist()],
        "chips": [round(float(x), 8) for x in chips.tolist()],
        "stats": _stats_payload(stats),
        "peaks": peaks,
        "series": [_history_row(row) for row in history],
        "meta": {
            "bins": int(len(centers)),
            "decay": _round(out.get("decay", DEFAULT_DECAY), 4),
            "peak": str(out.get("peak") or DEFAULT_PEAK),
            "rows": int(out.get("rows") or 0),
            "series": len(history),
            "unit": "turnover=%, chips=share(0~1)",
        },
    }


def chip_meta() -> dict[str, Any]:
    """筹码分布口径说明（前端抽屉 / 文档用）。"""
    return {
        "source": {
            "primary": "tonghuashun",
            "endpoint": "https://d.10jqka.com.cn/v6/line/hs_{code}/00/{last|year}.js",
            "fallback": "company.line.fetcher.fetch_kline（腾讯/东财/同花顺）",
            "adjust": "none",
        },
        "model": {
            "seed": "首日按当日三角分布铺满全部流通筹码",
            "decay": "旧筹码 × (1 - 有效换手) 衰减",
            "inject": "当日成交 × 有效换手，按三角分布注入",
            "effective_turnover": "min(1, 换手率/100 × decay)",
            "peak": "三角峰位置口径，默认 avg=成交额/成交量（通达信 / 同花顺客户端口径）",
            "peak_modes": {
                "avg": "成交额 / 成交量（成交均价，VWAP）",
                "ohlc4": "(O+H+L+C)/4",
                "typical": "(H+L+C)/3",
                "close": "收盘价",
            },
            "peak_fallback": "成交额缺失或单位对不上时，avg 退回 (O+H+L+C)/4",
            "bins": DEFAULT_BINS,
            "decay_param": DEFAULT_DECAY,
            "peak_param": DEFAULT_PEAK,
            "calibration": "GET /api/stocks/line-chip/calibrate 或 python -m company.analysis.line.chip "
            "--target-* ，用同花顺客户端读数反解 decay / peak",
        },
        "fields": {
            "grid": "价格轴（元）",
            "chips": "各价位筹码占比（合计 1）",
            "profit_ratio": "获利比例（收盘价以下筹码占比）",
            "avg_cost": "平均成本（元）",
            "cost70_low/cost70_high": "70% 成本区间（元）",
            "cost90_low/cost90_high": "90% 成本区间（元）",
            "concentration70/90": "(高-低)/(高+低)，越小越集中",
            "peak": "筹码峰价格（元）",
            "peaks": "筹码峰列表：[{price, weight, cum}]",
            "series": "每日统计序列：date/close/turnover/获利比例/成本区间/集中度",
        },
        "params": {
            "code": "股票代码，如 600519",
            "beg": "序列起始日，空则取最近 series_limit 个交易日",
            "end": "截止日，默认今天",
            "bins": f"价格分箱数 {MIN_BINS}~{MAX_BINS}，默认 {DEFAULT_BINS}",
            "decay": f"换手衰减系数，默认 {DEFAULT_DECAY}（同花顺口径）；"
            "1.5~2 会让历史筹码消散更快",
            "peak": f"三角峰口径，{'|'.join(PEAK_MODES)}，默认 {DEFAULT_PEAK}",
            "source": "auto|ths|fallback",
            "series_limit": "beg 为空时返回的序列长度上限，默认 250",
        },
    }
