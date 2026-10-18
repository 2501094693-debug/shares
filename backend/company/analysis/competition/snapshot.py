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

    view_results = _view_results(
        assets=assets,
        strat=strat,
        profit=profit,
        comp=comp,
        vals=vals,
        cost=cost,
        liab=liab,
        cash=cash,
        total_assets_val=total_assets_val,
        goodwill=goodwill,
        total_liab=total_liab,
        two_gold=two_gold,
        period_exp=period_exp,
        risk_hits=risk_hits,
        flags=flags,
        summary=summary,
        latest=latest,
        prev_rev=prev_rev,
        prev_core=prev_core,
        prev_ocf=prev_ocf,
    )

    return {
        "metrics": metrics,
        "view_results": view_results,
        "flags": flags,
        "risk_hits": risk_hits,
        "score_total": (summary or {}).get("score_total"),
        "strategy_type": strat.get("strategy_type") or "",
        "latest_period": period_label(latest),
        "report_date": str(latest.get("REPORT_DATE") or "")[:10],
    }


def _yi(value: Any) -> float | None:
    n = value if isinstance(value, (int, float)) else None
    return n / 1e8 if n is not None else None


def _view_results(
    *,
    assets: dict[str, Any],
    strat: dict[str, Any],
    profit: dict[str, Any],
    comp: dict[str, Any],
    vals: dict[str, Any],
    cost: dict[str, Any],
    liab: dict[str, Any],
    cash: dict[str, Any],
    total_assets_val: Any,
    goodwill: Any,
    total_liab: Any,
    two_gold: Any,
    period_exp: Any,
    risk_hits: Any,
    flags: list[str],
    summary: dict[str, Any] | None,
    latest: dict[str, Any],
    prev_rev: Any,
    prev_core: Any,
    prev_ocf: Any,
) -> dict[str, dict[str, Any]]:
    """把八看每一看的全部确定性计算结果整理成 {view_key: {result_key: value}}。"""

    def ratio(num: Any, den: Any) -> float | None:
        if num is None or not den:
            return None
        return num / den * 100

    return {
        "strategy": {
            "operating_assets": _yi(assets.get("operating_assets")),
            "operating_ratio": assets.get("operating_ratio"),
            "investing_assets": _yi(assets.get("investing_assets")),
            "investing_ratio": assets.get("investing_ratio"),
            "heavy_asset_ratio": strat.get("heavy_asset_ratio"),
            "goodwill_ratio": ratio(goodwill, total_assets_val),
            "strategy_type": strat.get("strategy_type") or "—",
        },
        "operating": {
            "two_ends_index": comp.get("two_ends_index"),
            "inventory_days": comp.get("inventory_turnover_days"),
            "receivable_days": comp.get("receivable_turnover_days"),
            "fixed_turnover": comp.get("fixed_asset_turnover"),
            "two_gold": _yi(two_gold),
            "two_gold_ratio": ratio(two_gold, total_assets_val),
            "gross_margin": profit.get("gross_margin"),
        },
        "profit": {
            "core_profit": _yi(profit.get("core_profit")),
            "core_margin": profit.get("core_margin"),
            "non_core_profit": _yi(profit.get("non_core_profit")),
            "deduct_ratio": profit.get("deduct_ratio"),
            "net_margin": profit.get("net_margin"),
        },
        "value": {
            "roe": profit.get("roe"),
            "roa": vals.get("roa"),
            "asset_turnover": vals.get("asset_turnover"),
            "equity_multiplier": vals.get("equity_multiplier"),
        },
        "cost": {
            "cogs_ratio": cost.get("营业成本率"),
            "sale_exp_ratio": cost.get("销售费用率"),
            "manage_exp_ratio": cost.get("管理费用率"),
            "rd_exp_ratio": cost.get("研发费用率"),
            "fin_exp_ratio": cost.get("财务费用率"),
            "period_exp_ratio": period_exp,
        },
        "quality": {
            "financial_liabilities": _yi(liab.get("financial_liabilities")),
            "financial_liab_ratio": liab.get("financial_ratio"),
            "operating_liabilities": _yi(liab.get("operating_liabilities")),
            "operating_liab_ratio": liab.get("operating_ratio"),
            "debt_ratio": ratio(total_liab, total_assets_val),
            "fcf": _yi(cash.get("fcf")),
            "ocf_core_ratio": cash.get("ocf_core_ratio"),
            "ocf_profit_ratio": cash.get("ocf_profit_ratio"),
            "cash_collection_ratio": cash.get("cash_collection_ratio"),
            "cashflow_mode": cash.get("cashflow_mode") or "—",
        },
        "risk": {
            "risk_hits": risk_hits,
            "risk_flags": "；".join(flags) if flags else "未触发",
        },
        "outlook": {
            "revenue_yoy": yoy(revenue(latest), prev_rev),
            "core_yoy": yoy(profit.get("core_profit"), prev_core),
            "ocf_yoy": yoy(operating_cash(latest), prev_ocf),
            "operating_asset_yoy": strat.get("operating_asset_yoy"),
            "investing_asset_yoy": strat.get("investing_asset_yoy"),
        },
        "summary": {
            "score_total": (summary or {}).get("score_total"),
        },
    }
