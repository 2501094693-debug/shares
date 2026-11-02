"""股票 vs 指数日线四项对比服务。

输入：起始日、股票、所选指数（可多选）。
输出：每日四项（开盘/收盘涨跌幅、最大涨跌幅）的方向与差值。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from company.analysis.line.compare.codes import (
    FACTOR_LABELS,
    FACTORS,
    catalog,
    factor_meta,
    resolve_indices,
)
from company.analysis.line.compare.score import pair_row, score_divergence
from company.analysis.line.compare.series import (
    factors_of,
    fetch_index_day,
    fetch_stock_day,
    slice_factors,
)


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or "")[:10]


def _trim_bars(
    bars: list[dict[str, Any]],
    *,
    beg: str,
    end: str,
    pad_days: int = 40,
) -> list[dict[str, Any]]:
    """裁到 ``[beg-pad, end]``，降低预取长序列上 factors_of 的开销。"""
    if not bars:
        return []
    try:
        lo = (
            datetime.strptime(str(beg)[:10], "%Y-%m-%d") - timedelta(days=int(pad_days))
        ).strftime("%Y-%m-%d")
    except ValueError:
        lo = str(beg)[:10]
    hi = str(end or beg)[:10]
    out = [b for b in bars if (d := _bar_date(b)) and lo <= d <= hi]
    return out or list(bars)


def _pct_block(row: dict[str, float | None]) -> dict[str, float | None]:
    """对外中文键 + 英文键双份，便于前端直接展示。"""
    out: dict[str, float | None] = {}
    for key in FACTORS:
        val = row.get(key)
        rounded = round(float(val), 6) if val is not None else None
        out[key] = rounded
        out[FACTOR_LABELS[key]] = rounded
    return out


def compare_one(
    stock_fac: dict[str, dict[str, float | None]],
    index_fac: dict[str, dict[str, float | None]],
    *,
    dates: list[str],
) -> dict[str, Any]:
    """单只指数对齐对比。"""
    daily: dict[str, list[dict[str, Any]]] = {f: [] for f in FACTORS}
    days: list[dict[str, Any]] = []

    for date in dates:
        s_row = stock_fac.get(date) or {}
        b_row = index_fac.get(date) or {}
        if not s_row or not b_row:
            continue
        day_factors: dict[str, Any] = {}
        ok = False
        for f in FACTORS:
            rs, rb = s_row.get(f), b_row.get(f)
            if rs is None or rb is None:
                continue
            paired = pair_row(float(rs), float(rb))
            paired["date"] = date
            daily[f].append(paired)
            day_factors[f] = paired
            ok = True
        if not ok:
            continue
        days.append(
            {
                "date": date,
                "stock": _pct_block(s_row),
                "index": _pct_block(b_row),
                "factors": day_factors,
            }
        )

    return {
        "dates": [d["date"] for d in days],
        "days": days,
        "daily": daily,
    }


def compare_stock_vs_indices(
    stock: str,
    *,
    beg: str,
    end: str = "",
    indices: str | list[str] | None = None,
) -> dict[str, Any]:
    """主入口：一只股票对比一只或多只指数。"""
    code = str(stock or "").strip()
    if not code:
        raise ValueError("缺少股票代码")
    if not beg:
        raise ValueError("缺少起始日期 beg")

    index_list = resolve_indices(indices)
    stock_pack = fetch_stock_day(code, beg=beg, end=end)
    stock_fac_all = factors_of(list(stock_pack.get("items") or []))
    end_eff = end or stock_pack["end"]
    stock_fac = slice_factors(stock_fac_all, beg=beg, end=end_eff)

    comparisons: list[dict[str, Any]] = []
    for meta in index_list:
        idx_code = meta["code"]
        idx_pack = fetch_index_day(idx_code, beg=beg, end=end)
        idx_fac_all = factors_of(list(idx_pack.get("items") or []))
        idx_fac = slice_factors(idx_fac_all, beg=beg, end=end or idx_pack["end"])
        dates = sorted(d for d in stock_fac if d in idx_fac)
        one = compare_one(stock_fac, idx_fac, dates=dates)
        comparisons.append(
            {
                "index": {
                    "code": str(idx_pack.get("code") or idx_code),
                    "name": str(idx_pack.get("name") or meta.get("name") or ""),
                    "source": str(idx_pack.get("source") or ""),
                },
                **one,
            }
        )

    return {
        "meta": {
            "stock": str(stock_pack.get("code") or code),
            "stock_name": str(stock_pack.get("name") or ""),
            "beg": stock_pack["beg"],
            "end": stock_pack["end"],
            "factors": factor_meta(),
            "stock_source": str(stock_pack.get("source") or ""),
        },
        "stock": {
            "code": str(stock_pack.get("code") or code),
            "name": str(stock_pack.get("name") or ""),
            "source": str(stock_pack.get("source") or ""),
            "adjust": "qfq",
        },
        "indices": [
            {"code": c["index"]["code"], "name": c["index"]["name"]} for c in comparisons
        ],
        "comparisons": comparisons,
    }


def compare_stock_vs_index(
    stock: str,
    index: str,
    *,
    beg: str,
    end: str = "",
) -> dict[str, Any]:
    """单指数便捷入口。"""
    pack = compare_stock_vs_indices(stock, beg=beg, end=end, indices=[index])
    if not pack["comparisons"]:
        raise ValueError("无对比结果")
    one = pack["comparisons"][0]
    return {
        "meta": {
            **pack["meta"],
            "index": one["index"]["code"],
            "index_name": one["index"]["name"],
            "n": len(one["dates"]),
        },
        "stock": pack.get("stock") or {},
        "index": one["index"],
        "dates": one["dates"],
        "days": one["days"],
        "daily": one["daily"],
    }


def compare_from_bars(
    stock: str,
    index: str,
    *,
    beg: str,
    end: str,
    stock_bars: list[dict[str, Any]],
    index_bars: list[dict[str, Any]],
    stock_name: str = "",
    stock_source: str = "",
    index_name: str = "",
    index_source: str = "",
) -> dict[str, Any]:
    """用已有日线算股指日级对比，跳过 ``fetch_stock_day`` / ``fetch_index_day``。"""
    code = str(stock or "").strip()
    idx = str(index or "").strip()
    if not code:
        raise ValueError("缺少股票代码")
    if not idx:
        raise ValueError("缺少指数代码")
    if not beg:
        raise ValueError("缺少起始日期 beg")
    end_eff = end or beg

    stock_fac = slice_factors(
        factors_of(_trim_bars(list(stock_bars or []), beg=beg, end=end_eff)),
        beg=beg,
        end=end_eff,
    )
    idx_fac = slice_factors(
        factors_of(_trim_bars(list(index_bars or []), beg=beg, end=end_eff)),
        beg=beg,
        end=end_eff,
    )
    dates = sorted(d for d in stock_fac if d in idx_fac)
    one = compare_one(stock_fac, idx_fac, dates=dates)
    return {
        "meta": {
            "stock": code,
            "stock_name": stock_name,
            "beg": beg,
            "end": end_eff,
            "index": idx,
            "index_name": index_name,
            "n": len(one["dates"]),
        },
        "stock": {
            "code": code,
            "name": stock_name,
            "source": stock_source,
            "adjust": "qfq",
        },
        "index": {
            "code": idx,
            "name": index_name,
            "source": index_source,
        },
        "dates": one["dates"],
        "days": one["days"],
        "daily": one["daily"],
    }


def compare_divergence(
    stock: str,
    index: str,
    *,
    beg: str,
    end: str = "",
    factor: str = "close",
    stock_bars: list[dict[str, Any]] | None = None,
    index_bars: list[dict[str, Any]] | None = None,
    stock_name: str = "",
    stock_source: str = "",
    index_name: str = "",
    index_source: str = "",
) -> dict[str, Any]:
    """区间股指反向偏离分：反向日数 / 有效日数 × 100。

    复用 ``compare_stock_vs_index`` 日级方向，再 ``score_divergence``。
    传入 ``stock_bars`` + ``index_bars`` 时可跳过二次拉数。
    ``factor`` 须为 open/high/low/close。
    """
    key = str(factor or "close").strip().lower()
    if key not in FACTORS:
        raise ValueError(f"不支持的对比口径 {factor!r}，可选 {FACTORS}")

    if stock_bars is not None and index_bars is not None:
        pack = compare_from_bars(
            stock,
            index,
            beg=beg,
            end=end or beg,
            stock_bars=stock_bars,
            index_bars=index_bars,
            stock_name=stock_name,
            stock_source=stock_source,
            index_name=index_name,
            index_source=index_source,
        )
    else:
        pack = compare_stock_vs_index(stock, index, beg=beg, end=end)
    rows = list((pack.get("daily") or {}).get(key) or [])
    scored = score_divergence(rows)
    return {
        "factor": key,
        "beg": (pack.get("meta") or {}).get("beg") or beg,
        "end": (pack.get("meta") or {}).get("end") or end,
        "stock": pack.get("stock") or {},
        "index": pack.get("index") or {},
        **scored,
    }


def available_indices() -> dict[str, Any]:
    return {
        "factors": factor_meta(),
        "indices": catalog(),
    }
