"""张新民「八看」规则引擎：全部指标由 Python 预计算。"""

from __future__ import annotations

from typing import Any

from agent.bazhang_analyst.rules._fields import (
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
from agent.comprehensive_analyst.rules._common import (
    fmt_num,
    fmt_pct,
    fmt_x,
    fmt_yi,
    md_table,
    period_label,
    pick,
    to_float,
    yoy,
)


def _sum_fields(row: dict[str, Any], fields: list[str]) -> float:
    total = 0.0
    found = False
    for key in fields:
        val = to_float(row.get(key))
        if val is not None:
            total += val
            found = True
    return total if found else 0.0


def _revenue(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *REVENUE_FIELDS))


def _net_profit(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *NET_PROFIT_FIELDS))


def _ocf(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *OCF_FIELDS))


def _total_assets(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *TOTAL_ASSETS_FIELDS))


def _classify_assets(row: dict[str, Any]) -> dict[str, Any]:
    operating = _sum_fields(row, OPERATING_ASSET_FIELDS)
    investing = _sum_fields(row, INVESTING_ASSET_FIELDS)
    total = _total_assets(row) or (operating + investing)
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
    }


def _classify_liabilities(row: dict[str, Any]) -> dict[str, Any]:
    financial = _sum_fields(row, FINANCIAL_LIABILITY_FIELDS)
    operating = _sum_fields(row, OPERATING_LIABILITY_FIELDS)
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


def _core_profit(row: dict[str, Any]) -> dict[str, Any]:
    revenue = _revenue(row)
    cogs = to_float(pick(row, *COGS_FIELDS))
    taxes = to_float(pick(row, *TAX_FIELDS))
    expenses = sum(_sum_fields(row, [f]) for f in CORE_PROFIT_EXPENSE_FIELDS)

    core = None
    if revenue is not None:
        core = revenue - (cogs or 0) - (taxes or 0) - expenses

    net = _net_profit(row)
    deduct = to_float(pick(row, *DEDUCT_PROFIT_FIELDS))
    non_core = (net - core) if net is not None and core is not None else None

    return {
        "revenue": revenue,
        "cogs": cogs,
        "taxes": taxes,
        "expenses": expenses,
        "core_profit": core,
        "core_margin": core / revenue * 100 if core is not None and revenue else None,
        "net_profit": net,
        "deduct_profit": deduct,
        "non_core_profit": non_core,
        "deduct_ratio": deduct / net * 100 if deduct is not None and net else None,
        "gross_margin": to_float(pick(row, "XSMLL")),
        "net_margin": to_float(pick(row, "XSJLL")),
        "roe": to_float(pick(row, "ROEJQ", "WEIGHTAVG_ROE")),
        "roic": to_float(pick(row, "ROIC")),
    }


def _cash_quality(latest: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, Any]:
    ocf = _ocf(latest)
    profit = _net_profit(latest)
    core = _core_profit(latest)["core_profit"]
    revenue = _revenue(latest)
    sales_cash = to_float(pick(latest, *SALES_CASH_FIELDS))
    capex = to_float(pick(latest, *CAPEX_FIELDS))
    icf = to_float(pick(latest, *ICF_FIELDS))
    fin_cf = to_float(pick(latest, *FCF_FIN_FIELDS))

    fcf = to_float(pick(latest, "FCFF_BACK", "FCFF_FORWARD"))
    if fcf is None and ocf is not None:
        fcf = ocf - (capex or 0)

    ocf_core_ratio = ocf / core * 100 if ocf is not None and core else None
    ocf_profit_ratio = ocf / profit * 100 if ocf is not None and profit else None
    cash_collection_ratio = sales_cash / revenue * 100 if sales_cash and revenue else None

    recv = to_float(pick(latest, "ACCOUNTS_RECE"))
    inventory = to_float(pick(latest, "INVENTORY"))
    prev_recv = to_float(pick(prev or {}, "ACCOUNTS_RECE")) if prev else None
    prev_inv = to_float(pick(prev or {}, "INVENTORY")) if prev else None
    prev_rev = _revenue(prev) if prev else None
    prev_core = _core_profit(prev)["core_profit"] if prev else None
    prev_ocf = _ocf(prev) if prev else None

    rev_yoy = yoy(revenue, prev_rev)
    recv_yoy = yoy(recv, prev_recv)
    inv_yoy = yoy(inventory, prev_inv)
    core_yoy = yoy(core, prev_core)
    ocf_yoy = yoy(ocf, prev_ocf)

    disconnections: list[str] = []
    if rev_yoy is not None and recv_yoy is not None and recv_yoy > rev_yoy * 1.5 and rev_yoy > 0:
        disconnections.append(f"应收增速({fmt_pct(recv_yoy)})显著快于营收增速({fmt_pct(rev_yoy)})")
    if rev_yoy is not None and inv_yoy is not None and inv_yoy > rev_yoy * 1.5 and rev_yoy > 0:
        disconnections.append(f"存货增速({fmt_pct(inv_yoy)})显著快于营收增速({fmt_pct(rev_yoy)})")
    if core_yoy is not None and ocf_yoy is not None and core_yoy > 10 and ocf_yoy < core_yoy * 0.5:
        disconnections.append(f"核心利润增长({fmt_pct(core_yoy)})与经营现金流增长({fmt_pct(ocf_yoy)})脱节")

    cashflow_mode = "未知"
    if ocf is not None:
        if ocf > 0 and (icf is None or icf < 0):
            cashflow_mode = "造血型（经营造血、投资支出）"
        elif ocf < 0 and icf and icf > 0:
            cashflow_mode = "输血型（经营失血、投资扩张）"
        elif fin_cf and fin_cf > 0 and (ocf is None or ocf < 0):
            cashflow_mode = "融资依赖型"
        else:
            cashflow_mode = "混合型"

    return {
        "ocf": ocf,
        "fcf": fcf,
        "capex": capex,
        "icf": icf,
        "fin_cf": fin_cf,
        "ocf_core_ratio": ocf_core_ratio,
        "ocf_profit_ratio": ocf_profit_ratio,
        "cash_collection_ratio": cash_collection_ratio,
        "cashflow_mode": cashflow_mode,
        "disconnections": disconnections,
        "rev_yoy": rev_yoy,
        "recv_yoy": recv_yoy,
        "inv_yoy": inv_yoy,
        "core_yoy": core_yoy,
        "ocf_yoy": ocf_yoy,
    }


def _competitiveness(row: dict[str, Any]) -> dict[str, Any]:
    liab = _classify_liabilities(row)
    assets = _classify_assets(row)
    recv = assets.get("receivables") or 0
    prepay = to_float(pick(row, "PREPAYMENT")) or 0
    payable = liab.get("accounts_payable") or 0
    advance = liab.get("advance_receivables") or 0

    upstream = payable + advance
    downstream = recv + prepay
    two_ends = upstream / downstream if downstream > 0 else None

    revenue = _revenue(row)
    cogs = to_float(pick(row, *COGS_FIELDS))
    fixed = assets.get("fixed_asset")
    inventory = assets.get("inventory")

    inv_turnover_days = 365 * inventory / cogs if inventory and cogs and cogs > 0 else None
    recv_turnover_days = 365 * recv / revenue if recv and revenue and revenue > 0 else None
    fixed_turnover = revenue / fixed if fixed and fixed > 0 and revenue else None

    return {
        "two_ends_index": two_ends,
        "upstream_occupy": upstream,
        "downstream_occupy": downstream,
        "inventory_turnover_days": inv_turnover_days,
        "receivable_turnover_days": recv_turnover_days,
        "fixed_asset_turnover": fixed_turnover,
    }


def _strategy_type(latest: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, Any]:
    assets = _classify_assets(latest)
    prev_assets = _classify_assets(prev) if prev else {}
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
    total = _total_assets(latest)
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


def _risk_flags(
    assets: dict[str, Any],
    liab: dict[str, Any],
    profit: dict[str, Any],
    cash: dict[str, Any],
    strategy: dict[str, Any],
) -> list[str]:
    flags: list[str] = []

    goodwill = assets.get("goodwill")
    total_assets_val = assets.get("operating_assets", 0) + assets.get("investing_assets", 0)
    if goodwill and total_assets_val and goodwill / total_assets_val > 0.15:
        flags.append(f"商誉占资产比重较高：{fmt_pct(goodwill / total_assets_val * 100)}")

    cash_val = assets.get("cash")
    short_loan = liab.get("short_loan")
    if cash_val and short_loan and cash_val > short_loan * 2 and short_loan > 0:
        flags.append("存贷双高迹象：货币资金充裕同时短期借款较高")

    debt_ratio = None
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


def _asset_structure_table(annual: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for row in annual[:5]:
        a = _classify_assets(row)
        total = _total_assets(row) or 1
        rows.append(
            [
                period_label(row),
                fmt_yi(a["operating_assets"]),
                fmt_pct(a["operating_ratio"]),
                fmt_yi(a["investing_assets"]),
                fmt_pct(a["investing_ratio"]),
                fmt_yi(a["fixed_asset"]),
                fmt_yi(a["goodwill"]),
                fmt_yi(a["two_gold"]),
                fmt_pct(a["two_gold"] / total * 100 if a["two_gold"] else None),
            ]
        )
    return md_table(
        ["报告期", "经营性资产", "占比", "投资性资产", "占比", "固定资产", "商誉", "两金合计", "两金占比"],
        rows,
    )


def _liability_structure_table(annual: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for row in annual[:5]:
        l = _classify_liabilities(row)
        rows.append(
            [
                period_label(row),
                fmt_yi(l["financial_liabilities"]),
                fmt_pct(l["financial_ratio"]),
                fmt_yi(l["operating_liabilities"]),
                fmt_pct(l["operating_ratio"]),
                fmt_yi(l["accounts_payable"]),
                fmt_yi(l["advance_receivables"]),
                fmt_yi(l["short_loan"]),
            ]
        )
    return md_table(
        ["报告期", "金融性负债", "占比", "经营性负债", "占比", "应付账款", "预收款项", "短期借款"],
        rows,
    )


def _core_profit_table(annual: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for row in annual[:5]:
        p = _core_profit(row)
        rows.append(
            [
                period_label(row),
                fmt_yi(p["revenue"]),
                fmt_yi(p["core_profit"]),
                fmt_pct(p["core_margin"]),
                fmt_yi(p["net_profit"]),
                fmt_yi(p["deduct_profit"]),
                fmt_pct(p["deduct_ratio"]),
                fmt_yi(p["non_core_profit"]),
            ]
        )
    return md_table(
        ["报告期", "营业收入", "核心利润", "核心利润率", "归母净利润", "扣非净利润", "扣非占比", "非核心损益"],
        rows,
    )


def _cash_quality_table(annual: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for i, row in enumerate(annual[:5]):
        prev = annual[i + 1] if i + 1 < len(annual) else None
        c = _cash_quality(row, prev)
        rows.append(
            [
                period_label(row),
                fmt_yi(c["ocf"]),
                fmt_yi(c["fcf"]),
                fmt_pct(c["ocf_core_ratio"]),
                fmt_pct(c["ocf_profit_ratio"]),
                fmt_pct(c["cash_collection_ratio"]),
                c["cashflow_mode"],
            ]
        )
    return md_table(
        ["报告期", "经营现金流", "自由现金流", "OCF/核心利润", "OCF/净利润", "销售收现比", "现金流模式"],
        rows,
    )


def _competitiveness_table(annual: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for row in annual[:5]:
        c = _competitiveness(row)
        rows.append(
            [
                period_label(row),
                fmt_x(c["two_ends_index"]),
                fmt_num(c["inventory_turnover_days"], 0) + "天" if c["inventory_turnover_days"] else "—",
                fmt_num(c["receivable_turnover_days"], 0) + "天" if c["receivable_turnover_days"] else "—",
                fmt_x(c["fixed_asset_turnover"]),
                fmt_pct(_core_profit(row)["gross_margin"]),
            ]
        )
    return md_table(
        ["报告期", "两头吃指数", "存货周转天数", "应收周转天数", "固定资产周转", "毛利率"],
        rows,
    )


def _cost_structure_table(annual: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for row in annual[:5]:
        rev = _revenue(row)
        if not rev:
            continue
        rows.append(
            [
                period_label(row),
                fmt_pct(to_float(pick(row, *COGS_FIELDS)) / rev * 100 if pick(row, *COGS_FIELDS) else None),
                fmt_pct(to_float(pick(row, "SALE_EXPENSE")) / rev * 100 if pick(row, "SALE_EXPENSE") else None),
                fmt_pct(to_float(pick(row, "MANAGE_EXPENSE")) / rev * 100 if pick(row, "MANAGE_EXPENSE") else None),
                fmt_pct(
                    to_float(pick(row, "RESEARCH_EXPENSE")) / rev * 100 if pick(row, "RESEARCH_EXPENSE") else None
                ),
                fmt_pct(to_float(pick(row, "FINANCE_EXPENSE")) / rev * 100 if pick(row, "FINANCE_EXPENSE") else None),
                fmt_pct(_core_profit(row)["gross_margin"]),
            ]
        )
    return md_table(
        ["报告期", "营业成本率", "销售费用率", "管理费用率", "研发费用率", "财务费用率", "毛利率"],
        rows,
    )


def _value_table(annual: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for row in annual[:5]:
        p = _core_profit(row)
        equity = to_float(pick(row, *TOTAL_EQUITY_FIELDS))
        rows.append(
            [
                period_label(row),
                fmt_pct(p["roe"]),
                fmt_pct(p["roic"]),
                fmt_pct(p["net_margin"]),
                fmt_yi(p["net_profit"]),
                fmt_yi(equity),
            ]
        )
    return md_table(["报告期", "ROE", "ROIC", "净利率", "归母净利润", "净资产"], rows)


def _diagnosis_table(metrics: dict[str, Any], flags: list[str]) -> str:
    def _grade(ratio: float | None, good: float, warn: float, higher_is_better: bool = True) -> str:
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

    cash = metrics.get("cash") or {}
    profit = metrics.get("profit") or {}
    rows = [
        ["战略一致性", metrics.get("strategy", {}).get("strategy_type", "—"), "—"],
        ["利润含金量", _grade(cash.get("ocf_core_ratio"), 100, 80), f"OCF/核心利润 {fmt_pct(cash.get('ocf_core_ratio'))}"],
        ["资产质量", "中" if len(flags) <= 2 else "差", f"警示 {len(flags)} 项"],
        ["竞争力", _grade(metrics.get("competitiveness", {}).get("two_ends_index"), 1.2, 0.8), f"两头吃 {fmt_x(metrics.get('competitiveness', {}).get('two_ends_index'))}"],
        ["价值创造", _grade(profit.get("roe"), 15, 8), f"ROE {fmt_pct(profit.get('roe'))}"],
    ]
    return md_table(["维度", "评价", "关键证据"], rows)


def run_zhang_analysis(
    annual: list[dict[str, Any]],
    recent: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """运行张新民「八看」全套规则引擎，返回指标、表格与警示。"""
    if not annual:
        return {
            "metrics": {},
            "flags": [],
            "tables": {},
            "text": "（未能获取财务报表数据）",
            "strategy_type": "未知",
        }

    latest = annual[0]
    prev = annual[1] if len(annual) > 1 else None

    assets = _classify_assets(latest)
    liab = _classify_liabilities(latest)
    profit = _core_profit(latest)
    cash = _cash_quality(latest, prev)
    comp = _competitiveness(latest)
    strategy = _strategy_type(latest, prev)
    flags = _risk_flags(assets, liab, profit, cash, strategy)

    metrics: dict[str, Any] = {
        "latest_period": period_label(latest),
        "assets": assets,
        "liabilities": liab,
        "profit": profit,
        "cash": cash,
        "competitiveness": comp,
        "strategy": strategy,
    }

    tables = {
        "asset_structure": _asset_structure_table(annual),
        "liability_structure": _liability_structure_table(annual),
        "core_profit": _core_profit_table(annual),
        "cash_quality": _cash_quality_table(annual),
        "competitiveness": _competitiveness_table(annual),
        "cost_structure": _cost_structure_table(annual),
        "value": _value_table(annual),
        "diagnosis": _diagnosis_table(metrics, flags),
    }

    text_parts = [
        f"### 战略类型：{strategy['strategy_type']}",
        f"- 经营性资产占比：{fmt_pct(strategy.get('operating_asset_ratio'))}",
        f"- 投资性资产占比：{fmt_pct(strategy.get('investing_asset_ratio'))}",
        f"- 重资产指数（固定资产/总资产）：{fmt_pct(strategy.get('heavy_asset_ratio'))}",
        "",
        "### 核心利润（最近年报）",
        f"- 核心利润：{fmt_yi(profit.get('core_profit'))}，核心利润率 {fmt_pct(profit.get('core_margin'))}",
        f"- 归母净利润：{fmt_yi(profit.get('net_profit'))}，扣非占比 {fmt_pct(profit.get('deduct_ratio'))}",
        "",
        "### 利润含金量",
        f"- 经营现金流/核心利润：{fmt_pct(cash.get('ocf_core_ratio'))}",
        f"- 经营现金流/净利润：{fmt_pct(cash.get('ocf_profit_ratio'))}",
        f"- 销售收现比：{fmt_pct(cash.get('cash_collection_ratio'))}",
        f"- 现金流模式：{cash.get('cashflow_mode')}",
        "",
        "### 竞争力",
        f"- 两头吃指数：{fmt_x(comp.get('two_ends_index'))}（>1 表示对上下游占款能力强）",
        f"- 存货周转天数：{fmt_num(comp.get('inventory_turnover_days'), 0)}天",
        f"- 应收周转天数：{fmt_num(comp.get('receivable_turnover_days'), 0)}天",
        "",
        "### 风险警示",
    ]
    if flags:
        text_parts.extend(f"- ⚠ {f}" for f in flags)
    else:
        text_parts.append("- 暂无重大警示")

    return {
        "metrics": metrics,
        "flags": flags,
        "tables": tables,
        "text": "\n".join(text_parts),
        "strategy_type": strategy["strategy_type"],
        "recent_periods": [period_label(r) for r in (recent or annual[:4])],
    }
