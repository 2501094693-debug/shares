"""区间内四价涨跌幅的波动范围、均值与标准差。

输入：代码 + 起始日期（可选结束日期）；``kind=stock|index``。

- 基准：``起始日期之前最近一个交易日``的收盘价
- 区间：``[起始日, 结束日]`` 内的每个交易日
- 序列：每日的开盘价 / 最高价 / 最低价 / 收盘价各自相对基准收盘的涨跌幅，
  四价即四条数字序列
- 结论：四条序列各自的波动范围（最低 / 最高 / 极差）与涨跌幅均值、标准差

个股日线走 ``company.line.fetcher.fetch_kline``（默认 ``qfq``）；
指数日线走 ``exponent.fetch_kline``（东财→同花顺回退）。
与 ``service.compute_undulate`` 共用同一套基准与涨跌幅口径，只额外补统计量。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.codes import normalize_code

from company.analysis.line.undulate.service import (
    FACTOR_LABELS,
    FACTORS,
    _bar_date,
    _fetch_day_range,
    _iso,
    _today_iso,
    compute_undulate,
)
from company.analysis.line.undulate.stats import compute_stats


def _series_of(days: list[dict[str, Any]], factor: str) -> list[dict[str, Any]]:
    """把每日涨跌幅摊平成 ``[{date, pct}]``，缺值日跳过。"""
    out: list[dict[str, Any]] = []
    for day in days:
        pct = (day.get("pct") or {}).get(factor)
        if pct is None:
            continue
        out.append({"date": day.get("date"), "pct": pct})
    return out


def _stat_block(
    factor: str,
    days: list[dict[str, Any]],
    end_date: str = "",
) -> dict[str, Any]:
    """单因子：统计量 + 极值出现的日期 + 结束日的 z 值（σ 坐标）。"""
    series = _series_of(days, factor)
    stats = compute_stats([pt["pct"] for pt in series])

    min_date = max_date = None
    if series:
        min_date = min(series, key=lambda pt: pt["pct"])["date"]
        max_date = max(series, key=lambda pt: pt["pct"])["date"]

    # 结束日（区间最后一个交易日）该因子的涨跌幅及其在「均值=0、标准差=单位」坐标轴上的位置
    end_pct: float | None = None
    end_z: float | None = None
    if end_date:
        for pt in series:
            if pt["date"] == end_date:
                end_pct = float(pt["pct"])
                break
    mean = stats["mean"]
    std = stats["std"]
    if end_pct is not None and mean is not None and std is not None and std > 0:
        end_z = round((end_pct - mean) / std, 6)
    # 结束日涨跌幅直接换算为以标准差为单位（pct / σ），与 K 线 σ 轴口径一致
    end_sigma: float | None = None
    if end_pct is not None and std is not None and std > 0:
        end_sigma = round(end_pct / std, 6)

    return {
        "factor": factor,
        "label": FACTOR_LABELS[factor],
        "count": stats["count"],
        "min": stats["min"],
        "max": stats["max"],
        "range": stats["range"],
        "mean": stats["mean"],
        "std": stats["std"],
        "min_date": min_date,
        "max_date": max_date,
        "end_date": end_date or None,
        "end_pct": end_pct,
        "end_z": end_z,
        "end_sigma": end_sigma,
        "series": series,
    }


def compute_volatility(
    bars: list[dict[str, Any]],
    beg: str,
    end: str = "",
) -> dict[str, Any]:
    """在已排序日线序列上算四价涨跌幅的波动范围 / 均值 / 标准差（纯函数）。

    基准与区间口径完全复用 ``compute_undulate``，因此两者的基准日、
    区间交易日数量、每日涨跌幅都一致，只是这里多了统计汇总。
    """
    base = compute_undulate(bars, beg, end)
    days = list(base.get("days") or [])
    used_end = str(base.get("end") or "")

    stats: dict[str, dict[str, Any]] = {
        factor: _stat_block(factor, days, used_end) for factor in FACTORS
    }

    return {
        **base,
        "stats": stats,
        # 便于「四个数字序列」直接取用的扁平版本
        "series": {factor: stats[factor]["series"] for factor in FACTORS},
    }


def _norm_index_code(code: str) -> str:
    raw = str(code or "").strip()
    if not raw:
        return ""
    # 允许 1.000001 / sh000001 等形式，取末段数字公开码
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 6:
        return digits[-6:]
    return digits or raw


def _fetch_index_day_range(
    code: str,
    *,
    beg_iso: str,
    end_iso: str,
) -> dict[str, Any]:
    """拉指数日线：覆盖 [beg, end]，并多取 beg 前若干根以拿到基准收盘。"""
    from exponent import fetch_kline

    pad = (
        datetime.strptime(beg_iso, "%Y-%m-%d") - timedelta(days=40)
    ).strftime("%Y%m%d")
    end_compact = end_iso.replace("-", "")
    # 同花顺优先：东财外网偶发 RemoteDisconnected / 长时间挂起，会让指数统计比个股慢很多。
    # 与前端左下指数图（fetchLcIndexKline）保持同一取数优先级。
    sources = ("tonghuashun", "eastmoney")
    last_err: Exception | None = None
    for source in sources:
        try:
            pack = fetch_kline(
                code,
                source=source,
                period="day",
                beg=pad,
                end=end_compact,
                limit=5000,
            )
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
        items = list(pack.get("items") or [])
        if not items:
            last_err = ValueError(f"{source} 空 K 线")
            continue
        items.sort(key=_bar_date)
        return {
            "code": str(pack.get("code") or code),
            "name": str(pack.get("name") or ""),
            "source": str(pack.get("source") or source),
            "items": items,
        }
    raise ValueError(str(last_err) if last_err else "指数日线加载失败")


def analyze_volatility(
    code: str,
    beg: str,
    end: str = "",
    *,
    adjust: str = "qfq",
    kind: str = "stock",
) -> dict[str, Any]:
    """主入口：区间内四价涨跌幅的波动范围、均值与标准差。

    ``kind=stock`` 用个股前复权日线；``kind=index`` 用指数日线（不复权）。
    """
    kind_key = (kind or "stock").strip().lower()
    if kind_key not in ("stock", "index"):
        raise ValueError(f"kind 须为 stock|index，收到 {kind!r}")

    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else _today_iso()
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")

    if kind_key == "index":
        norm = _norm_index_code(code)
        if not norm:
            raise ValueError("无效指数代码")
        hist = _fetch_index_day_range(norm, beg_iso=beg_iso, end_iso=end_iso)
        result = compute_volatility(list(hist.get("items") or []), beg_iso, end_iso)
        return {
            "code": str(hist.get("code") or norm),
            "name": str(hist.get("name") or ""),
            "source": str(hist.get("source") or ""),
            "kind": "index",
            "adjust": "none",
            **result,
        }

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    hist = _fetch_day_range(
        norm, beg_iso=beg_iso, end_iso=end_iso, adjust=adjust
    )
    result = compute_volatility(list(hist.get("items") or []), beg_iso, end_iso)

    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "kind": "stock",
        "adjust": adjust,
        **result,
    }
