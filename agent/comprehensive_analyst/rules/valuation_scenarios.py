"""三情景估值计算（乐观 / 中性 / 悲观）。"""

from __future__ import annotations

from typing import Any

from agent.comprehensive_analyst.rules._common import fmt_num, fmt_pct, md_table, to_float


def _percentile(vals: list[float], pct: float) -> float | None:
    if not vals:
        return None
    xs = sorted(vals)
    k = (len(xs) - 1) * pct / 100
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def _median(vals: list[float]) -> float | None:
    return _percentile(vals, 50)


def _valuation_stats(pe_items: list[dict[str, Any]], field: str) -> dict[str, float | None]:
    vals = []
    for item in pe_items:
        n = to_float(item.get(field))
        if n is not None and n > 0:
            vals.append(n)
    if not vals:
        return {"current": None, "p25": None, "p50": None, "p75": None, "min": None, "max": None}
    latest = to_float(pe_items[-1].get(field)) if pe_items else None
    return {
        "current": latest,
        "p25": _percentile(vals, 25),
        "p50": _median(vals),
        "p75": _percentile(vals, 75),
        "min": min(vals),
        "max": max(vals),
    }


def compute_valuation_scenarios(
    stock: dict[str, Any],
    annual: list[dict[str, Any]],
    pe_items: list[dict[str, Any]],
    *,
    growth_optimistic: float = 0.15,
    growth_neutral: float = 0.08,
    growth_pessimistic: float = 0.03,
) -> dict[str, Any]:
    """计算 PE/PB/PS/FCF 三情景目标价。"""
    price = to_float(stock.get("price") or stock.get("_price_raw"))
    pe_ttm = to_float(stock.get("pe_ttm"))
    pb = to_float(stock.get("pb"))
    ps_ttm = to_float(stock.get("ps_ttm"))
    eps = to_float(stock.get("eps"))
    bvps = to_float(stock.get("bvps"))
    mcap = to_float(stock.get("_mcap_raw"))
    if mcap is None:
        cap_text = str(stock.get("market_cap") or "")
        cap_n = to_float(cap_text.replace("亿", ""))
        if cap_n is not None:
            mcap = cap_n * 1e8

    if (eps is None or eps <= 0) and price and pe_ttm and pe_ttm > 0:
        eps = price / pe_ttm

    latest_annual = annual[0] if annual else {}
    shares = to_float(
        latest_annual.get("TOTAL_SHARE")
        or latest_annual.get("A_FREE_SHARE")
        or stock.get("total_shares")
    )

    fcf = None
    if latest_annual:
        ocf = to_float(latest_annual.get("NETCASH_OPERATE_PK") or latest_annual.get("NETCASH_OPERATE"))
        capex = to_float(latest_annual.get("CONSTRUCT_LONG_ASSET"))
        fcf_direct = to_float(latest_annual.get("FCFF_BACK") or latest_annual.get("FCFF_FORWARD"))
        if fcf_direct is not None:
            fcf = fcf_direct
        elif ocf is not None:
            fcf = ocf - (capex or 0)
    fcf_ps = (fcf / shares) if fcf is not None and shares else None

    pe_stats = _valuation_stats(pe_items, "pe_ttm")
    pb_stats = _valuation_stats(pe_items, "pb")
    ps_stats = _valuation_stats(pe_items, "ps_ttm")

    revenue_ps = None
    if ps_ttm and price and ps_ttm > 0:
        revenue_ps = price / ps_ttm

    scenarios: dict[str, dict[str, Any]] = {}
    for name, pe_mult, pb_mult, ps_mult, growth, fcf_mult in (
        ("optimistic", pe_stats["p75"], pb_stats["p75"], ps_stats["p75"], growth_optimistic, 15),
        ("neutral", pe_stats["p50"], pb_stats["p50"], ps_stats["p50"], growth_neutral, 12),
        ("pessimistic", pe_stats["p25"], pb_stats["p25"], ps_stats["p25"], growth_pessimistic, 8),
    ):
        targets: dict[str, float | None] = {}
        if eps and pe_mult:
            targets["pe"] = eps * (1 + growth) * pe_mult
        if bvps and pb_mult:
            targets["pb"] = bvps * pb_mult
        if revenue_ps and ps_mult:
            targets["ps"] = revenue_ps * (1 + growth) * ps_mult
        if fcf_ps:
            targets["fcf"] = fcf_ps * fcf_mult

        valid = [v for v in targets.values() if v and v > 0]
        composite = sum(valid) / len(valid) if valid else None
        upside = ((composite - price) / price * 100) if composite and price else None

        scenarios[name] = {
            "label": {"optimistic": "乐观", "neutral": "中性", "pessimistic": "悲观"}[name],
            "growth": growth,
            "pe_target": targets.get("pe"),
            "pb_target": targets.get("pb"),
            "ps_target": targets.get("ps"),
            "fcf_target": targets.get("fcf"),
            "composite": composite,
            "upside_pct": upside,
            "assumptions": (
                f"利润增速 {fmt_pct(growth * 100)}；"
                f"PE 倍数 {fmt_num(pe_mult)}；PB {fmt_num(pb_mult)}；"
                f"PS {fmt_num(ps_mult)}；FCF 倍数 {fcf_mult}x"
            ),
        }

    summary_rows: list[list[str]] = []
    for key in ("optimistic", "neutral", "pessimistic"):
        s = scenarios[key]
        summary_rows.append(
            [
                s["label"],
                fmt_num(s["pe_target"]),
                fmt_num(s["pb_target"]),
                fmt_num(s["ps_target"]),
                fmt_num(s["fcf_target"]),
                fmt_num(s["composite"]),
                fmt_pct(s["upside_pct"]) if s["upside_pct"] is not None else "—",
            ]
        )

    stats_text = (
        f"当前价 {fmt_num(price)} | PE_TTM {fmt_num(pe_ttm)} | PB {fmt_num(pb)} | PS_TTM {fmt_num(ps_ttm)}\n\n"
        f"历史 PE 分位：25% {fmt_num(pe_stats['p25'])} / 中位 {fmt_num(pe_stats['p50'])} / 75% {fmt_num(pe_stats['p75'])}\n"
        f"历史 PB 分位：25% {fmt_num(pb_stats['p25'])} / 中位 {fmt_num(pb_stats['p50'])} / 75% {fmt_num(pb_stats['p75'])}\n"
        f"历史 PS 分位：25% {fmt_num(ps_stats['p25'])} / 中位 {fmt_num(ps_stats['p50'])} / 75% {fmt_num(ps_stats['p75'])}"
    )

    table = md_table(
        ["情景", "PE法", "PB法", "PS法", "FCF法", "综合目标价", "较现价空间"],
        summary_rows,
    )

    disclaimer = (
        "> 以上为程序预计算参考区间，综合目标价为各有效方法算术平均。"
        "不构成投资建议；解读时需说明假设与局限性。"
    )

    return {
        "scenarios": scenarios,
        "pe_stats": pe_stats,
        "pb_stats": pb_stats,
        "ps_stats": ps_stats,
        "price": price,
        "text": f"{stats_text}\n\n### 三情景估值汇总\n{table}\n\n{disclaimer}",
        "table": summary_rows,
    }
