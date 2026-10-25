"""股票 vs 指数日线四项对比服务。

输入：起始日、股票、所选指数（可多选）。
输出：每日四项（开盘/收盘涨跌幅、最大涨跌幅）的方向与差值；
强弱/偏离默认按波动标准化（zdif = rs/σs − rb/σb）。
"""

from __future__ import annotations

from typing import Any

from company.analysis.line.compare.codes import (
    FACTOR_LABELS,
    FACTORS,
    catalog,
    factor_meta,
    resolve_indices,
)
from company.analysis.line.compare.score import (
    VOL_MIN_PERIODS,
    pair_row,
    range_sigma,
    summarize_all,
)
from company.analysis.line.compare.series import (
    factors_of,
    fetch_index_day,
    fetch_stock_day,
    slice_factors,
)


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
    """单只指数对齐对比；σ 用 dates 闭区间内样本标准差（每因子各一个）。"""
    sigma_s = {f: range_sigma(stock_fac, f, dates) for f in FACTORS}
    sigma_b = {f: range_sigma(index_fac, f, dates) for f in FACTORS}

    daily: dict[str, list[dict[str, Any]]] = {f: [] for f in FACTORS}
    days: list[dict[str, Any]] = []
    vol_n = 0
    raw_n = 0

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
            paired = pair_row(
                float(rs),
                float(rb),
                sigma_s=sigma_s[f],
                sigma_b=sigma_b[f],
            )
            paired["date"] = date
            daily[f].append(paired)
            day_factors[f] = paired
            if paired.get("norm") == "vol":
                vol_n += 1
            else:
                raw_n += 1
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

    summary = summarize_all(daily)
    return {
        "dates": [d["date"] for d in days],
        "days": days,
        "daily": daily,
        "scores": summary["scores"],
        "deviations": summary["deviations"],
        "dirs": summary["dirs"],
        "total": summary["total"],
        "deviation": summary["deviation"],
        "norm": {
            **summary["norm"],
            "sigma": {
                "stock": {f: sigma_s[f] for f in FACTORS},
                "index": {f: sigma_b[f] for f in FACTORS},
            },
            "vol_pairs": vol_n,
            "raw_pairs": raw_n,
        },
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
        # σ 仅用对齐后的选区闭区间 [beg, end]
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

    mode = "vol"
    if comparisons:
        mode = str((comparisons[0].get("norm") or {}).get("mode") or "vol")

    return {
        "meta": {
            "stock": str(stock_pack.get("code") or code),
            "stock_name": str(stock_pack.get("name") or ""),
            "beg": stock_pack["beg"],
            "end": stock_pack["end"],
            "factors": factor_meta(),
            "stock_source": str(stock_pack.get("source") or ""),
            "norm": {
                "mode": mode,
                "scope": "range",
                "min_periods": VOL_MIN_PERIODS,
                "unit": "sigma" if mode == "vol" else "pct_point",
                "label": "波动标准化(选区)" if mode == "vol" else "裸百分点",
            },
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
        "dates": one["dates"],
        "days": one["days"],
        "daily": one["daily"],
        "scores": one["scores"],
        "deviations": one["deviations"],
        "dirs": one["dirs"],
        "total": one["total"],
        "deviation": one["deviation"],
        "norm": one.get("norm") or pack["meta"].get("norm"),
    }


def available_indices() -> dict[str, Any]:
    return {
        "factors": factor_meta(),
        "indices": catalog(),
        "norm": {
            "mode": "vol",
            "scope": "range",
            "min_periods": VOL_MIN_PERIODS,
            "unit": "sigma",
            "label": "波动标准化(选区)",
        },
    }
