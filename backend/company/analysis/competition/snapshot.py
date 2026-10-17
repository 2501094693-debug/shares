"""单公司八看指标快照：供横截面比对使用的扁平指标字典。

全部复用 ``company.analysis.financialreport.metrics`` 的确定性计算，不引入模型。
输入是已按同口径选好、最新在前的 ``series``（至少 1 期，最好 2 期以算同比）。
"""

from __future__ import annotations

from typing import Any

from company.analysis.financialreport._common import period_label, yoy
from company.analysis.financialreport.metrics import (
    cash_quality,
    classify_assets,
    classify_liabilities,
    competitiveness,
    core_profit,
    cost_structure,
    operating_cash,
    revenue,
    strategy_type,
    total_assets,
    value_parts,
)
from company.analysis.financialreport.views import _risk_items, build_summary


def _safe(fn: Any) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


def _ratio(num: Any, den: Any) -> float | None:
    if num is None or not den:
        return None
    return num / den * 100


def build_snapshot(series: list[dict[str, Any]]) -> dict[str, Any]:
    """把一家公司的同口径序列压成一行横截面指标。

    返回：``{metrics: {...}, flags, risk_hits, score_total, strategy_type,
    latest_period, report_date, stale_parent}``。
    """
    if not series:
        return {
            "metrics": {},
            "flags": [],
            "risk_hits": None,
            "score_total": None,
            "strategy_type": "",
            "latest_period": "",
            "report_date": "",
        }

    latest = series[0]
    prev = series[1] if len(series) > 1 else None

    assets = classify_assets(latest)
    liab = classify_liabilities(latest)
    profit = core_profit(latest)
    cash = cash_quality(latest, prev)
    comp = competitiveness(latest)
    strat = strategy_type(latest, prev)
    vals = value_parts(latest, profit)
    cost = cost_structure(latest).get("rates", {})

    total_assets_val = total_assets(latest) or (assets.get("operating_assets", 0) + assets.get("investing_assets", 0))
    goodwill = assets.get("goodwill")
    total_liab = liab.get("total_liabilities")
    two_gold = assets.get("two_gold")
    period_exp = (
        sum((cost.get(k) or 0) for k in ("销售费用率", "管理费用率", "研发费用率", "财务费用率"))
        if revenue(latest)
        else None
    )

    risk_items, risk_hits = _risk_items(series) if series else ([], 0)
    flags = [item["name"] for item in risk_items if item.get("triggered")]

    summary = _safe(lambda: build_summary(series, {"strategy": strat, "profit": profit, "cash": cash, "competitiveness": comp}, coverage=""))

    prev_rev = revenue(prev) if prev else None
    prev_core = core_profit(prev)["core_profit"] if prev else None
    prev_ocf = operating_cash(prev) if prev else None

    metrics: dict[str, Any] = {
        # 一看
        "operating_ratio": assets.get("operating_ratio"),
        "investing_ratio": assets.get("investing_ratio"),
        "heavy_asset_ratio": strat.get("heavy_asset_ratio"),
        "goodwill_ratio": _ratio(goodwill, total_assets_val),
        "strategy_type": strat.get("strategy_type"),
        # 二看
        "two_ends_index": comp.get("two_ends_index"),
        "inventory_days": comp.get("inventory_turnover_days"),
        "receivable_days": comp.get("receivable_turnover_days"),
        "fixed_turnover": comp.get("fixed_asset_turnover"),
        "gross_margin": profit.get("gross_margin"),
        "two_gold_ratio": _ratio(two_gold, total_assets_val),
        # 三看
        "core_profit": profit.get("core_profit") / 1e8 if profit.get("core_profit") is not None else None,
        "core_margin": profit.get("core_margin"),
        "deduct_ratio": profit.get("deduct_ratio"),
        "net_margin": profit.get("net_margin"),
        # 四看
        "roe": profit.get("roe"),
        "roa": vals.get("roa"),
        "asset_turnover": vals.get("asset_turnover"),
        "equity_multiplier": vals.get("equity_multiplier"),
        # 五看
        "cogs_ratio": cost.get("营业成本率"),
        "sale_exp_ratio": cost.get("销售费用率"),
        "manage_exp_ratio": cost.get("管理费用率"),
        "rd_exp_ratio": cost.get("研发费用率"),
        "fin_exp_ratio": cost.get("财务费用率"),
        "period_exp_ratio": period_exp,
        # 六看
        "debt_ratio": _ratio(total_liab, total_assets_val),
        "financial_liab_ratio": liab.get("financial_ratio"),
        "operating_liab_ratio": liab.get("operating_ratio"),
        "ocf_core_ratio": cash.get("ocf_core_ratio"),
        "ocf_profit_ratio": cash.get("ocf_profit_ratio"),
        "cash_collection_ratio": cash.get("cash_collection_ratio"),
        "fcf": cash.get("fcf") / 1e8 if cash.get("fcf") is not None else None,
        # 七看
        "risk_hits": risk_hits,
        # 八看
        "revenue_yoy": yoy(revenue(latest), prev_rev),
        "core_yoy": yoy(profit.get("core_profit"), prev_core),
        "ocf_yoy": yoy(operating_cash(latest), prev_ocf),
        # 综合
        "score_total": (summary or {}).get("score_total"),
    }

    return {
        "metrics": metrics,
        "flags": flags,
        "risk_hits": risk_hits,
        "score_total": (summary or {}).get("score_total"),
        "strategy_type": strat.get("strategy_type") or "",
        "latest_period": period_label(latest),
        "report_date": str(latest.get("REPORT_DATE") or "")[:10],
    }
