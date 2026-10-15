"""张新民「八看」：指标计算层。

全部为确定性 Python 计算，不依赖任何模型。八看视图只消费这里算好的数字。
"""

from __future__ import annotations

from typing import Any

from company.analysis.financialreport._common import (
    fmt_pct,
    pick,
    period_label,
    report_kind,
    to_float,
    yoy,
)
from company.analysis.financialreport._fields import (
    CAPEX_FIELDS,
    COGS_FIELDS,
    CORE_PROFIT_EXPENSE_FIELDS,
    DEDUCT_PROFIT_FIELDS,
    FCF_FIN_FIELDS,
    FINANCIAL_LIABILITY_FIELDS,
    ICF_FIELDS,
    INVESTING_ASSET_FIELDS,
    NET_PROFIT_FIELDS,
    OCF_FIELDS,
    OPERATING_ASSET_FIELDS,
    OPERATING_LIABILITY_FIELDS,
    REVENUE_FIELDS,
    SALES_CASH_FIELDS,
    TAX_FIELDS,
    TOTAL_ASSETS_FIELDS,
    TOTAL_EQUITY_FIELDS,
    TOTAL_LIAB_FIELDS,
)


def sum_fields(row: dict[str, Any], fields: list[str]) -> float:
    total = 0.0
    found = False
    for key in fields:
        val = to_float(row.get(key))
        if val is not None:
            total += val
            found = True
    return total if found else 0.0


def revenue(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *REVENUE_FIELDS))


def net_profit(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *NET_PROFIT_FIELDS))


def operating_cash(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *OCF_FIELDS))


def total_assets(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *TOTAL_ASSETS_FIELDS))


def _gross_margin(row: dict[str, Any], rev: float | None = None, cogs: float | None = None) -> float | None:
    disclosed = to_float(pick(row, "XSMLL"))
    if disclosed is not None:
        return disclosed
    if rev is None:
        rev = revenue(row)
    if cogs is None:
        cogs = to_float(pick(row, *COGS_FIELDS))
    if rev and cogs is not None:
        return (rev - cogs) / rev * 100
    return None


def classify_assets(row: dict[str, Any]) -> dict[str, Any]:
    """一看：经营性资产 / 投资性资产拆分。"""
    operating = sum_fields(row, OPERATING_ASSET_FIELDS)
    investing = sum_fields(row, INVESTING_ASSET_FIELDS)
    total = total_assets(row) or (operating + investing)
    if total <= 0:
        total = operating + investing
    return {
        "operating_assets": operating,
        "investing_assets": investing,
        "operating_ratio": operating / total * 100 if total else None,
        "investing_ratio": investing / total * 100 if total else None,
        "fixed_asset": to_float(pick(row, "FIXED_ASSET")),
        "goodwill": to_float(pick(row, "GOODWILL")),
        "long_equity_invest": to_float(pick(row, "LONG_EQUITY_INVEST")),
        "cash": to_float(pick(row, "MONETARYFUNDS")),
        "receivables": to_float(pick(row, "ACCOUNTS_RECE")),
        "inventory": to_float(pick(row, "INVENTORY")),
        "two_gold": (to_float(pick(row, "ACCOUNTS_RECE")) or 0) + (to_float(pick(row, "INVENTORY")) or 0),
        "total_assets": total,
    }


def classify_liabilities(row: dict[str, Any]) -> dict[str, Any]:
    """六看：金融性负债 / 经营性负债拆分。"""
    financial = sum_fields(row, FINANCIAL_LIABILITY_FIELDS)
    operating = sum_fields(row, OPERATING_LIABILITY_FIELDS)
    total_liab = to_float(pick(row, *TOTAL_LIAB_FIELDS)) or (financial + operating)
    return {
        "financial_liabilities": financial,
        "operating_liabilities": operating,
        "total_liabilities": total_liab,
        "financial_ratio": financial / total_liab * 100 if total_liab else None,
        "operating_ratio": operating / total_liab * 100 if total_liab else None,
        "accounts_payable": to_float(pick(row, "ACCOUNTS_PAYABLE")),
        "advance_receivables": to_float(pick(row, "ADVANCE_RECEIVABLES", "CONTRACT_LIAB")),
        "short_loan": to_float(pick(row, "SHORT_LOAN")),
    }


def core_profit(row: dict[str, Any]) -> dict[str, Any]:
    """三看：核心利润（张新民定义）。"""
    rev = revenue(row)
    cogs = to_float(pick(row, *COGS_FIELDS))
    taxes = to_float(pick(row, *TAX_FIELDS))
    expenses = sum(sum_fields(row, [field]) for field in CORE_PROFIT_EXPENSE_FIELDS)

    core = rev - (cogs or 0) - (taxes or 0) - expenses if rev is not None else None
    net = net_profit(row)
    deduct = to_float(pick(row, *DEDUCT_PROFIT_FIELDS))
    non_core = (net - core) if net is not None and core is not None else None

    return {
        "revenue": rev,
        "cogs": cogs,
        "taxes": taxes,
        "expenses": expenses,
        "core_profit": core,
        "core_margin": core / rev * 100 if core is not None and rev else None,
        "net_profit": net,
        "deduct_profit": deduct,
        "non_core_profit": non_core,
        "deduct_ratio": deduct / net * 100 if deduct is not None and net else None,
        "gross_margin": _gross_margin(row, rev, cogs),
        "net_margin": to_float(pick(row, "XSJLL")),
        "roe": to_float(pick(row, "ROEJQ", "WEIGHTAVG_ROE")),
        "roic": to_float(pick(row, "ROIC")),
    }


def cash_quality(latest: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, Any]:
    """六看：利润含金量 + 三脱节 + 现金流模式。"""
    ocf = operating_cash(latest)
    profit = net_profit(latest)
    core = core_profit(latest)["core_profit"]
    rev = revenue(latest)
    sales_cash = to_float(pick(latest, *SALES_CASH_FIELDS))
    capex = to_float(pick(latest, *CAPEX_FIELDS))
    icf = to_float(pick(latest, *ICF_FIELDS))
    fin_cf = to_float(pick(latest, *FCF_FIN_FIELDS))

    fcf = to_float(pick(latest, "FCFF_BACK", "FCFF_FORWARD"))
    if fcf is None and ocf is not None:
        fcf = ocf - (capex or 0)

    recv = to_float(pick(latest, "ACCOUNTS_RECE"))
    inventory = to_float(pick(latest, "INVENTORY"))
    prev_row = prev or {}
    rev_yoy = yoy(rev, revenue(prev_row) if prev else None)
    recv_yoy = yoy(recv, to_float(pick(prev_row, "ACCOUNTS_RECE")) if prev else None)
    inv_yoy = yoy(inventory, to_float(pick(prev_row, "INVENTORY")) if prev else None)
    core_yoy = yoy(core, core_profit(prev_row)["core_profit"] if prev else None)
    ocf_yoy = yoy(ocf, operating_cash(prev_row) if prev else None)

    disconnections: list[str] = []
    if rev_yoy is not None and recv_yoy is not None and recv_yoy > rev_yoy * 1.5 and rev_yoy > 0:
        disconnections.append(f"应收增速({fmt_pct(recv_yoy)})显著快于营收增速({fmt_pct(rev_yoy)})")
    if rev_yoy is not None and inv_yoy is not None and inv_yoy > rev_yoy * 1.5 and rev_yoy > 0:
        disconnections.append(f"存货增速({fmt_pct(inv_yoy)})显著快于营收增速({fmt_pct(rev_yoy)})")
    if core_yoy is not None and ocf_yoy is not None and core_yoy > 10 and ocf_yoy < core_yoy * 0.5:
        disconnections.append(f"核心利润增长({fmt_pct(core_yoy)})与经营现金流增长({fmt_pct(ocf_yoy)})脱节")

    if ocf is None:
        cashflow_mode = "未知"
    elif ocf > 0 and (icf is None or icf < 0):
        cashflow_mode = "造血型（经营造血、投资支出）"
    elif ocf < 0 and icf and icf > 0:
        cashflow_mode = "输血型（经营失血、投资扩张）"
    elif fin_cf and fin_cf > 0 and ocf < 0:
        cashflow_mode = "融资依赖型"
    else:
        cashflow_mode = "混合型"

    return {
        "ocf": ocf,
        "fcf": fcf,
        "capex": capex,
        "icf": icf,
        "fin_cf": fin_cf,
        "ocf_core_ratio": ocf / core * 100 if ocf is not None and core else None,
        "ocf_profit_ratio": ocf / profit * 100 if ocf is not None and profit else None,
        "cash_collection_ratio": sales_cash / rev * 100 if sales_cash and rev else None,
        "cashflow_mode": cashflow_mode,
        "disconnections": disconnections,
        "rev_yoy": rev_yoy,
        "recv_yoy": recv_yoy,
        "inv_yoy": inv_yoy,
        "core_yoy": core_yoy,
        "ocf_yoy": ocf_yoy,
    }


def competitiveness(row: dict[str, Any]) -> dict[str, Any]:
    """二看：两头吃指数、周转效率。"""
    liab = classify_liabilities(row)
    assets = classify_assets(row)
    recv = assets.get("receivables") or 0
    prepay = to_float(pick(row, "PREPAYMENT")) or 0
    payable = liab.get("accounts_payable") or 0
    advance = liab.get("advance_receivables") or 0

    upstream = payable + advance
    downstream = recv + prepay
    two_ends = upstream / downstream if downstream > 0 else None

    rev = revenue(row)
    cogs = to_float(pick(row, *COGS_FIELDS))
    fixed = assets.get("fixed_asset")
    inventory = assets.get("inventory")

    return {
        "two_ends_index": two_ends,
        "upstream_occupy": upstream,
        "downstream_occupy": downstream,
        "inventory_turnover_days": 365 * inventory / cogs if inventory and cogs and cogs > 0 else None,
        "receivable_turnover_days": 365 * recv / rev if recv and rev and rev > 0 else None,
        "fixed_asset_turnover": rev / fixed if fixed and fixed > 0 and rev else None,
    }


def strategy_type(latest: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, Any]:
    """一看：经营主导 / 投资主导 / 混合型 判定。"""
    assets = classify_assets(latest)
    prev_assets = classify_assets(prev) if prev else {}
    op_ratio = assets.get("operating_ratio")
    inv_ratio = assets.get("investing_ratio")
    op_yoy = yoy(assets.get("operating_assets"), prev_assets.get("operating_assets"))
    inv_yoy = yoy(assets.get("investing_assets"), prev_assets.get("investing_assets"))

    if inv_ratio is not None and inv_ratio > 35 and (inv_yoy or 0) > (op_yoy or 0):
        stype = "投资主导型"
    elif op_ratio is not None and op_ratio > 65:
        stype = "经营主导型"
    else:
        stype = "混合型"

    heavy_asset = None
    total = total_assets(latest)
    fixed = assets.get("fixed_asset")
    if total and fixed:
        heavy_asset = fixed / total * 100

    return {
        "strategy_type": stype,
        "operating_asset_ratio": op_ratio,
        "investing_asset_ratio": inv_ratio,
        "operating_asset_yoy": op_yoy,
        "investing_asset_yoy": inv_yoy,
        "heavy_asset_ratio": heavy_asset,
    }


def cost_structure(row: dict[str, Any]) -> dict[str, Any]:
    """五看：成本费用率。"""
    rev = revenue(row)
    if not rev:
        return {}
    cogs = to_float(pick(row, *COGS_FIELDS))
    items = {
        "营业成本率": cogs / rev * 100 if cogs is not None else None,
        "销售费用率": (to_float(pick(row, "SALE_EXPENSE")) or 0) / rev * 100 if pick(row, "SALE_EXPENSE") else None,
        "管理费用率": (to_float(pick(row, "MANAGE_EXPENSE")) or 0) / rev * 100 if pick(row, "MANAGE_EXPENSE") else None,
        "研发费用率": (to_float(pick(row, "RESEARCH_EXPENSE")) or 0) / rev * 100 if pick(row, "RESEARCH_EXPENSE") else None,
        "财务费用率": (to_float(pick(row, "FINANCE_EXPENSE")) or 0) / rev * 100 if pick(row, "FINANCE_EXPENSE") else None,
        "毛利率": core_profit(row).get("gross_margin"),
    }
    ranked = sorted(
        ((k, v) for k, v in items.items() if v is not None and k != "毛利率"),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return {"rates": items, "ranked": ranked}


def value_parts(row: dict[str, Any], profit: dict[str, Any]) -> dict[str, Any]:
    """四看：杜邦拆解。"""
    assets = total_assets(row)
    equity = to_float(pick(row, *TOTAL_EQUITY_FIELDS))
    rev = profit.get("revenue")
    net = profit.get("net_profit")
    roa = to_float(pick(row, "ZZCJLL"))
    if roa is None and net is not None and assets:
        roa = net / assets * 100
    return {
        "roa": roa,
        "asset_turnover": (rev / assets) if rev and assets else None,
        "equity_multiplier": (assets / equity) if assets and equity else None,
        "equity": equity,
    }


def risk_flags(
    assets: dict[str, Any],
    liab: dict[str, Any],
    profit: dict[str, Any],
    cash: dict[str, Any],
    strategy: dict[str, Any],
) -> list[str]:
    """七看：风险警示清单（全部硬阈值）。"""
    del strategy
    flags: list[str] = []

    total_assets_val = (assets.get("operating_assets", 0) + assets.get("investing_assets", 0)) or 0
    goodwill = assets.get("goodwill")
    if goodwill and total_assets_val and goodwill / total_assets_val > 0.15:
        flags.append(f"商誉占资产比重较高：{fmt_pct(goodwill / total_assets_val * 100)}")

    cash_val = assets.get("cash")
    short_loan = liab.get("short_loan")
    if cash_val and short_loan and cash_val > short_loan * 2 and short_loan > 0:
        flags.append("存贷双高迹象：货币资金充裕同时短期借款较高")

    if liab.get("total_liabilities") and total_assets_val:
        debt_ratio = liab["total_liabilities"] / total_assets_val * 100
        if debt_ratio > 70:
            flags.append(f"资产负债率偏高：{fmt_pct(debt_ratio)}")

    if liab.get("financial_ratio") and liab["financial_ratio"] > 60:
        flags.append(f"金融性负债占比较高：{fmt_pct(liab['financial_ratio'])}")

    if profit.get("deduct_ratio") and profit["deduct_ratio"] < 70:
        flags.append(f"扣非净利润占归母净利润比例偏低：{fmt_pct(profit['deduct_ratio'])}")

    if cash.get("ocf_profit_ratio") is not None and cash["ocf_profit_ratio"] < 80:
        flags.append(f"经营现金流/净利润偏低：{fmt_pct(cash['ocf_profit_ratio'])}")

    if cash.get("ocf_core_ratio") is not None and cash["ocf_core_ratio"] < 80:
        flags.append(f"经营现金流/核心利润偏低：{fmt_pct(cash['ocf_core_ratio'])}")

    flags.extend(cash.get("disconnections") or [])

    two_gold = assets.get("two_gold")
    if two_gold and total_assets_val and two_gold / total_assets_val > 0.4:
        flags.append(f"两金（应收+存货）占资产比重较高：{fmt_pct(two_gold / total_assets_val * 100)}")

    return flags


def grade(ratio: float | None, good: float, warn: float, higher_is_better: bool = True) -> str:
    """统一评级：优 / 中 / 差。"""
    if ratio is None:
        return "—"
    if higher_is_better:
        if ratio >= good:
            return "优"
        if ratio >= warn:
            return "中"
        return "差"
    if ratio <= good:
        return "优"
    if ratio <= warn:
        return "中"
    return "差"


def compute_bundle(series: list[dict[str, Any]]) -> dict[str, Any]:
    """对同口径序列算出最新一期的八看指标集合，供各视图与汇总复用。"""
    latest = series[0] if series else {}
    prev = series[1] if len(series) > 1 else None
    assets = classify_assets(latest)
    liab = classify_liabilities(latest)
    profit = core_profit(latest)
    cash = cash_quality(latest, prev)
    comp = competitiveness(latest)
    strategy = strategy_type(latest, prev)
    flags = risk_flags(assets, liab, profit, cash, strategy)
    return {
        "latest": latest,
        "prev": prev,
        "latest_period": period_label(latest),
        "period_kind": report_kind(latest),
        "assets": assets,
        "liabilities": liab,
        "profit": profit,
        "cash": cash,
        "competitiveness": comp,
        "strategy": strategy,
        "flags": flags,
    }

