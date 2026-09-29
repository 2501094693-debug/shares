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
from agent.rules._common import (
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


PERIOD_LIMIT = 8
RECENT_LIMIT = 12


def _sum_fields(row: dict[str, Any], fields: list[str]) -> float:
    total = 0.0
    found = False
    for key in fields:
        val = to_float(row.get(key))
        if val is not None:
            total += val
            found = True
    return total if found else 0.0


def _compose_step(
    *,
    raw: str,
    formulas: list[tuple[str, str]],
    results: str,
    conclusions: list[str] | None,
) -> str:
    """每一步固定顺序：原始数据 → 计算公式 → 计算结果 → 结论。"""
    formula_md = (
        md_table(["指标", "计算公式"], [[name, formula] for name, formula in formulas])
        if formulas
        else "（本节无二次加工公式）"
    )
    conc = [item for item in (conclusions or []) if item]
    conc_md = "\n".join(f"- {item}" for item in conc) if conc else "- 数据不足，暂不下结论"
    return "\n".join(
        [
            "#### 原始数据",
            "",
            (raw or "").strip() or "（无原始科目）",
            "",
            "#### 计算公式",
            "",
            formula_md,
            "",
            "#### 计算结果",
            "",
            (results or "").strip() or "（无计算结果）",
            "",
            "#### 结论",
            "",
            conc_md,
        ]
    )


def _raw_md(rows: list[dict[str, Any]], columns: list[tuple[str, Any]], *, limit: int | None = None) -> str:
    cap = PERIOD_LIMIT if limit is None else limit
    body: list[list[str]] = []
    for row in rows[:cap]:
        cells = [period_label(row)]
        for _, getter in columns:
            if callable(getter):
                cells.append(str(getter(row)))
            elif isinstance(getter, (list, tuple)):
                cells.append(fmt_yi(to_float(pick(row, *getter))))
            else:
                cells.append(fmt_yi(to_float(pick(row, getter))))
        body.append(cells)
    return md_table(["报告期"] + [name for name, _ in columns], body)


def _pct_col(*keys: str):
    def _fn(row: dict[str, Any]) -> str:
        return fmt_pct(to_float(pick(row, *keys)))

    return _fn


def _ytd_note(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    kind = period_kind(row)
    if kind == "年报":
        return ""
    return f"{period_label(row)}为{kind}累计口径，利润表/现金流量表不可与年报直接横比。"


def period_kind(row: dict[str, Any]) -> str:
    label = str(row.get("PERIOD_LABEL") or "")
    if "三季" in label:
        return "三季报"
    if "半年" in label or "中报" in label:
        return "半年报"
    if "一季" in label:
        return "一季报"
    if "年报" in label:
        return "年报"
    day = str(row.get("REPORT_DATE") or row.get("REPORTDATE") or "")[:10]
    if day.endswith("-12-31"):
        return "年报"
    if day.endswith("-09-30"):
        return "三季报"
    if day.endswith("-06-30"):
        return "半年报"
    if day.endswith("-03-31"):
        return "一季报"
    return "定期报告"


def select_periodic_rows(
    *,
    annual: list[dict[str, Any]] | None = None,
    recent: list[dict[str, Any]] | None = None,
    merged: list[dict[str, Any]] | None = None,
    limit: int = PERIOD_LIMIT,
) -> list[dict[str, Any]]:
    """取最新一期定期报告，并抽出同一报告类型的历史期（三季报对三季报）。"""
    pool = list(merged or recent or annual or [])
    if not pool:
        return []
    kind = period_kind(pool[0])
    same = [row for row in pool if period_kind(row) == kind]
    if same:
        return same[:limit]
    return pool[:limit]


def _gross_margin(
    row: dict[str, Any],
    revenue: float | None = None,
    cogs: float | None = None,
) -> float | None:
    disclosed = to_float(pick(row, "XSMLL"))
    if disclosed is not None:
        return disclosed
    if revenue is None:
        revenue = _revenue(row)
    if cogs is None:
        cogs = to_float(pick(row, *COGS_FIELDS))
    if revenue and cogs is not None:
        return (revenue - cogs) / revenue * 100
    return None


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
        "gross_margin": _gross_margin(row, revenue, cogs),
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


def _asset_conclusions(rows: list[dict[str, Any]]) -> list[str]:
    latest = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    assets = _classify_assets(latest)
    strategy = _strategy_type(latest, prev)
    total = _total_assets(latest) or ((assets.get("operating_assets") or 0) + (assets.get("investing_assets") or 0))
    two_gold_pct = assets["two_gold"] / total * 100 if assets.get("two_gold") and total else None
    bullets = [
        _ytd_note(latest),
        (
            f"{period_label(latest)}经营性资产 {fmt_yi(assets.get('operating_assets'))}"
            f"（占比 {fmt_pct(strategy.get('operating_asset_ratio'))}），"
            f"投资性资产 {fmt_yi(assets.get('investing_assets'))}"
            f"（占比 {fmt_pct(strategy.get('investing_asset_ratio'))}）。"
            f"判定规则：投资占比>35%且投资增速快于经营 → 投资主导；经营占比>65% → 经营主导；否则混合。"
            f"本期判定为 **{strategy.get('strategy_type')}**。"
        ),
        (
            f"经营性资产同比 {fmt_pct(strategy.get('operating_asset_yoy'))}，"
            f"投资性资产同比 {fmt_pct(strategy.get('investing_asset_yoy'))}。"
            if prev
            else ""
        ),
        f"两金（应收+存货）{fmt_yi(assets.get('two_gold'))}，占总资产 {fmt_pct(two_gold_pct)}"
        + ("，占用偏高（>40%）" if two_gold_pct and two_gold_pct > 40 else "")
        + "。",
        f"重资产指数（固定资产÷总资产）{fmt_pct(strategy.get('heavy_asset_ratio'))}。",
    ]
    return [item for item in bullets if item]


def _liability_conclusions(rows: list[dict[str, Any]]) -> list[str]:
    latest = rows[0]
    liab = _classify_liabilities(latest)
    assets = _classify_assets(latest)
    bullets = [
        _ytd_note(latest),
        (
            f"{period_label(latest)}金融性负债 {fmt_yi(liab.get('financial_liabilities'))}"
            f"（占负债 {fmt_pct(liab.get('financial_ratio'))}），"
            f"经营性负债 {fmt_yi(liab.get('operating_liabilities'))}"
            f"（占负债 {fmt_pct(liab.get('operating_ratio'))}）。"
        ),
    ]
    fin_r, op_r = liab.get("financial_ratio"), liab.get("operating_ratio")
    if fin_r is not None and op_r is not None:
        if op_r > fin_r:
            bullets.append("经营性负债高于金融性负债，更多依靠占用上下游商业信用，而非有息融资。")
        elif fin_r > 60:
            bullets.append("金融性负债占比超过60%，对有息债务依赖偏高。")
        else:
            bullets.append("有息负债与经营性负债并存，需结合现金流看偿债压力。")
    cash_val, short_loan = assets.get("cash"), liab.get("short_loan")
    if cash_val and short_loan and cash_val > short_loan * 2 and short_loan > 0:
        bullets.append(
            f"货币资金 {fmt_yi(cash_val)} 同时短期借款 {fmt_yi(short_loan)}，存在存贷双高迹象。"
        )
    return [item for item in bullets if item]


def _core_profit_conclusions(rows: list[dict[str, Any]]) -> list[str]:
    latest = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    p = _core_profit(latest)
    prev_p = _core_profit(prev) if prev else None
    gm, cm = p.get("gross_margin"), p.get("core_margin")
    gap = (gm - cm) if gm is not None and cm is not None else None
    bullets = [
        _ytd_note(latest),
        (
            f"代入公式：营业收入 {fmt_yi(p.get('revenue'))} − 营业成本 {fmt_yi(p.get('cogs'))}"
            f" − 税金及附加 {fmt_yi(p.get('taxes'))} − 销售/管理/研发/财务费用 {fmt_yi(p.get('expenses'))}"
            f" = 核心利润 {fmt_yi(p.get('core_profit'))}，核心利润率 {fmt_pct(p.get('core_margin'))}。"
        ),
        f"毛利率 {fmt_pct(gm)}"
        + (f"，与核心利润率相差 {fmt_num(gap, 2)} 个百分点，差距来自税金及期间费用。" if gap is not None else "。"),
    ]
    if prev_p:
        core_yoy = yoy(p.get("core_profit"), prev_p.get("core_profit"))
        bullets.append(
            f"相对上一期同口径{period_label(prev)}核心利润 {fmt_yi(prev_p.get('core_profit'))}，"
            f"本期核心利润同比 {fmt_pct(core_yoy)}。"
        )
    deduct = p.get("deduct_ratio")
    if deduct is not None:
        quality = "经常性利润占比较高" if deduct >= 70 else "扣非占比偏低，利润含非经常损益干扰"
        bullets.append(f"扣非净利润占归母净利润 {fmt_pct(deduct)}，{quality}。")
    return [item for item in bullets if item]


def _cash_conclusions(rows: list[dict[str, Any]]) -> list[str]:
    latest = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    c = _cash_quality(latest, prev)
    grade = _grade(c.get("ocf_core_ratio"), 100, 80)
    bullets = [
        _ytd_note(latest),
        (
            f"{period_label(latest)}经营现金流 {fmt_yi(c.get('ocf'))}，自由现金流 {fmt_yi(c.get('fcf'))}。"
            f"OCF/核心利润 {fmt_pct(c.get('ocf_core_ratio'))}（≥100%优、≥80%中），评价为 **{grade}**。"
        ),
        f"OCF/净利润 {fmt_pct(c.get('ocf_profit_ratio'))}，销售收现比 {fmt_pct(c.get('cash_collection_ratio'))}。",
        f"现金流模式：{c.get('cashflow_mode')}。",
    ]
    disc = c.get("disconnections") or []
    if disc:
        bullets.extend(disc)
    else:
        bullets.append("未见应收/存货增速显著快于营收，或核心利润与经营现金流增长脱节。")
    return [item for item in bullets if item]


def _competitiveness_conclusions(rows: list[dict[str, Any]]) -> list[str]:
    latest = rows[0]
    c = _competitiveness(latest)
    p = _core_profit(latest)
    idx = c.get("two_ends_index")
    if idx is None:
        power = "分母（应收+预付）为0，无法计算两头吃指数"
    elif idx > 1:
        power = ">1，对上下游占款能力强"
    elif idx >= 0.8:
        power = "接近1，占款能力中性"
    else:
        power = "<1，更多被上下游占用资金"
    bullets = [
        _ytd_note(latest),
        (
            f"代入公式：（应付账款+预收）{fmt_yi(c.get('upstream_occupy'))}"
            f" ÷（应收账款+预付）{fmt_yi(c.get('downstream_occupy'))}"
            f" = 两头吃指数 {fmt_x(idx)}，{power}。"
        ),
        (
            f"存货周转天数 {fmt_num(c.get('inventory_turnover_days'), 0)}天"
            f"（365×存货÷营业成本），应收周转天数 {fmt_num(c.get('receivable_turnover_days'), 0)}天"
            f"（365×应收账款÷营业收入），固定资产周转 {fmt_x(c.get('fixed_asset_turnover'))}。"
        ),
        f"毛利率 {fmt_pct(p.get('gross_margin'))}，评价竞争力时与两头吃指数一并看。",
    ]
    return [item for item in bullets if item]


def _cost_conclusions(rows: list[dict[str, Any]]) -> list[str]:
    latest = next((row for row in rows if _revenue(row)), None)
    if not latest:
        return ["营业收入缺失，无法拆成本结构。"]
    rev = _revenue(latest) or 0
    cogs = to_float(pick(latest, *COGS_FIELDS))
    items = [
        ("营业成本率", to_float(pick(latest, *COGS_FIELDS)) / rev * 100 if cogs is not None and rev else None),
        ("销售费用率", to_float(pick(latest, "SALE_EXPENSE")) / rev * 100 if pick(latest, "SALE_EXPENSE") and rev else None),
        ("管理费用率", to_float(pick(latest, "MANAGE_EXPENSE")) / rev * 100 if pick(latest, "MANAGE_EXPENSE") and rev else None),
        ("研发费用率", to_float(pick(latest, "RESEARCH_EXPENSE")) / rev * 100 if pick(latest, "RESEARCH_EXPENSE") and rev else None),
        ("财务费用率", to_float(pick(latest, "FINANCE_EXPENSE")) / rev * 100 if pick(latest, "FINANCE_EXPENSE") and rev else None),
    ]
    ranked = [(name, val) for name, val in items if val is not None]
    ranked.sort(key=lambda kv: kv[1], reverse=True)
    top = f"占比最高的是{ranked[0][0]} {fmt_pct(ranked[0][1])}" if ranked else "各项费用率数据不足"
    gm = _core_profit(latest).get("gross_margin")
    return [
        _ytd_note(latest),
        f"{period_label(latest)}营业收入 {fmt_yi(rev)}，{top}。",
        f"毛利率 {fmt_pct(gm)}。营业成本率与毛利率互为对照：毛利率优先取披露数，缺省时用 1−营业成本率。",
    ]


def _value_conclusions(rows: list[dict[str, Any]]) -> list[str]:
    latest = rows[0]
    p = _core_profit(latest)
    d = _dupont_parts(latest, p)
    roe = p.get("roe")
    grade = _grade(roe, 15, 8)
    bullets = [
        _ytd_note(latest),
        f"{period_label(latest)}ROE {fmt_pct(roe)}（≥15%优、≥8%中），评价为 **{grade}**；ROA {fmt_pct(d.get('roa'))}，ROIC {fmt_pct(p.get('roic'))}。",
        (
            f"杜邦拆解：净利率 {fmt_pct(p.get('net_margin'))} × 资产周转 {fmt_x(d.get('asset_turnover'))}"
            f" × 权益乘数 {fmt_x(d.get('equity_multiplier'))}。"
        ),
        f"归母净利润 {fmt_yi(p.get('net_profit'))}，净资产 {fmt_yi(d.get('equity'))}。",
    ]
    return [item for item in bullets if item]


def _snapshot_conclusions(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["未能获取定期报告。"]
    counts: dict[str, int] = {}
    for row in rows[:RECENT_LIMIT]:
        kind = period_kind(row)
        counts[kind] = counts.get(kind, 0) + 1
    latest = rows[0]
    p = _core_profit(latest)
    cover = "、".join(f"{kind}{n}期" for kind, n in counts.items())
    return [
        f"按报告日落最新的定期报告排列，覆盖 {cover}。利润表/现金流量表为累计数，不同类型报告期不可直接横比。",
        (
            f"最新一期 {period_label(latest)}（{period_kind(latest)}）营业收入 {fmt_yi(p.get('revenue'))}，"
            f"核心利润 {fmt_yi(p.get('core_profit'))}，核心利润率 {fmt_pct(p.get('core_margin'))}。"
        ),
    ]


def _diagnosis_conclusions(metrics: dict[str, Any], flags: list[str], rows: list[list[str]]) -> list[str]:
    bullets = [
        f"数据覆盖：{metrics.get('coverage') or '—'}。最新定期报告 {metrics.get('latest_period') or '—'}（{metrics.get('period_kind') or '定期报告'}）。"
    ]
    for dim, grade, evidence in rows:
        if dim in {"最新定期报告", "数据覆盖"}:
            continue
        bullets.append(f"{dim}：{grade}（{evidence}）。")
    if flags:
        bullets.append("风险警示：" + "；".join(flags) + "。")
    else:
        bullets.append("规则引擎未触发重大风险警示。")
    return bullets


def _asset_structure_table(annual: list[dict[str, Any]]) -> str:
    raw = "\n\n".join(
        [
            _raw_md(
                annual,
                [
                    ("货币资金", "MONETARYFUNDS"),
                    ("应收票据", "NOTE_RECE"),
                    ("应收账款", "ACCOUNTS_RECE"),
                    ("预付款项", "PREPAYMENT"),
                    ("存货", "INVENTORY"),
                    ("合同资产", "CONTRACT_ASSET"),
                    ("固定资产", "FIXED_ASSET"),
                    ("在建工程", "CIP"),
                    ("无形资产", "INTANGIBLE_ASSET"),
                ],
            ),
            _raw_md(
                annual,
                [
                    ("长期股权投资", "LONG_EQUITY_INVEST"),
                    ("商誉", "GOODWILL"),
                    ("投资性房地产", "INVEST_REALESTATE"),
                    ("其他权益工具投资", "OTHER_EQUITY_INVEST"),
                    ("交易性金融资产", "TRADE_FINASSET_NOTFVTPL"),
                    ("总资产", TOTAL_ASSETS_FIELDS),
                ],
            ),
        ]
    )
    rows: list[list[str]] = []
    for row in annual[:PERIOD_LIMIT]:
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
    return _compose_step(
        raw=raw,
        formulas=[
            ("经营性资产", "货币资金、应收、预付、存货、固定资产、在建工程、无形资产等经营占用项合计"),
            ("投资性资产", "长期股权投资、商誉、金融资产、投资性房地产等合计"),
            ("两金合计", "应收账款 + 存货"),
            ("两金占比", "两金合计 ÷ 总资产"),
            ("战略类型", "投资占比>35%且投资增速>经营增速 → 投资主导；经营占比>65% → 经营主导；否则混合"),
        ],
        results=md_table(
            ["报告期", "经营性资产", "占比", "投资性资产", "占比", "固定资产", "商誉", "两金合计", "两金占比"],
            rows,
        ),
        conclusions=_asset_conclusions(annual),
    )


def _liability_structure_table(annual: list[dict[str, Any]]) -> str:
    raw = "\n\n".join(
        [
            _raw_md(
                annual,
                [
                    ("短期借款", "SHORT_LOAN"),
                    ("长期借款", "LONG_LOAN"),
                    ("应付债券", "BOND_PAYABLE"),
                    ("应付短期债券", "SHORT_BOND_PAYABLE"),
                    ("租赁负债", "LEASE_LIABILITY"),
                    ("一年内到期非流动负债", "NONCURRENT_LIAB_1YEAR"),
                    ("负债合计", TOTAL_LIAB_FIELDS),
                ],
            ),
            _raw_md(
                annual,
                [
                    ("应付账款", "ACCOUNTS_PAYABLE"),
                    ("应付票据", "NOTE_PAYABLE"),
                    ("预收/合同负债", ("ADVANCE_RECEIVABLES", "CONTRACT_LIAB")),
                    ("应付职工薪酬", "STAFF_SALARY_PAYABLE"),
                    ("应交税费", "TAX_PAYABLE"),
                    ("其他应付款", "TOTAL_OTHER_PAYABLE"),
                    ("货币资金", "MONETARYFUNDS"),
                ],
            ),
        ]
    )
    rows: list[list[str]] = []
    for row in annual[:PERIOD_LIMIT]:
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
    return _compose_step(
        raw=raw,
        formulas=[
            ("金融性负债", "短期借款 + 长期借款 + 应付债券 + 应付短期债券 + 租赁负债 + 一年内到期非流动负债"),
            ("经营性负债", "应付账款 + 应付票据 + 预收/合同负债 + 应付职工薪酬 + 应交税费 + 其他应付款"),
            ("金融/经营占比", "对应负债 ÷ 负债合计"),
        ],
        results=md_table(
            ["报告期", "金融性负债", "占比", "经营性负债", "占比", "应付账款", "预收款项", "短期借款"],
            rows,
        ),
        conclusions=_liability_conclusions(annual),
    )


def _core_profit_table(annual: list[dict[str, Any]]) -> str:
    raw = _raw_md(
        annual,
        [
            ("营业收入", REVENUE_FIELDS),
            ("营业成本", COGS_FIELDS),
            ("税金及附加", TAX_FIELDS),
            ("销售费用", "SALE_EXPENSE"),
            ("管理费用", "MANAGE_EXPENSE"),
            ("研发费用", "RESEARCH_EXPENSE"),
            ("财务费用", "FINANCE_EXPENSE"),
            ("归母净利润", NET_PROFIT_FIELDS),
            ("扣非净利润", DEDUCT_PROFIT_FIELDS),
            ("披露毛利率", _pct_col("XSMLL")),
        ],
    )
    rows: list[list[str]] = []
    for row in annual[:PERIOD_LIMIT]:
        p = _core_profit(row)
        rows.append(
            [
                period_label(row),
                fmt_yi(p["revenue"]),
                fmt_yi(p["core_profit"]),
                fmt_pct(p["core_margin"]),
                fmt_pct(p["gross_margin"]),
                fmt_yi(p["net_profit"]),
                fmt_yi(p["deduct_profit"]),
                fmt_pct(p["deduct_ratio"]),
                fmt_yi(p["non_core_profit"]),
            ]
        )
    return _compose_step(
        raw=raw,
        formulas=[
            ("核心利润", "营业收入 − 营业成本 − 税金及附加 − 销售/管理/研发/财务费用"),
            ("核心利润率", "核心利润 ÷ 营业收入"),
            ("毛利率", "优先取利润表主要指标；未披露时按 (营业收入 − 营业成本) ÷ 营业收入"),
            ("扣非占比", "扣非净利润 ÷ 归母净利润"),
            ("非核心损益", "归母净利润 − 核心利润"),
        ],
        results=md_table(
            ["报告期", "营业收入", "核心利润", "核心利润率", "毛利率", "归母净利润", "扣非净利润", "扣非占比", "非核心损益"],
            rows,
        ),
        conclusions=_core_profit_conclusions(annual),
    )


def _cash_quality_table(annual: list[dict[str, Any]]) -> str:
    raw = _raw_md(
        annual,
        [
            ("经营现金流", OCF_FIELDS),
            ("投资现金流", ICF_FIELDS),
            ("筹资现金流", FCF_FIN_FIELDS),
            ("购建固定资产等", CAPEX_FIELDS),
            ("销售商品收现", SALES_CASH_FIELDS),
            ("归母净利润", NET_PROFIT_FIELDS),
            ("营业收入", REVENUE_FIELDS),
            ("应收账款", "ACCOUNTS_RECE"),
            ("存货", "INVENTORY"),
        ],
    )
    rows: list[list[str]] = []
    for i, row in enumerate(annual[:PERIOD_LIMIT]):
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
    return _compose_step(
        raw=raw,
        formulas=[
            ("自由现金流", "优先取 FCFF；缺省时 经营现金流 − 购建固定资产等资本开支"),
            ("OCF/核心利润", "经营现金流 ÷ 核心利润"),
            ("OCF/净利润", "经营现金流 ÷ 归母净利润"),
            ("销售收现比", "销售商品提供劳务收到的现金 ÷ 营业收入"),
            ("利润含金量评价", "OCF/核心利润 ≥100% 优，≥80% 中，否则差"),
        ],
        results=md_table(
            ["报告期", "经营现金流", "自由现金流", "OCF/核心利润", "OCF/净利润", "销售收现比", "现金流模式"],
            rows,
        ),
        conclusions=_cash_conclusions(annual),
    )


def _competitiveness_table(annual: list[dict[str, Any]]) -> str:
    raw = _raw_md(
        annual,
        [
            ("应付账款", "ACCOUNTS_PAYABLE"),
            ("预收/合同负债", ("ADVANCE_RECEIVABLES", "CONTRACT_LIAB")),
            ("应收账款", "ACCOUNTS_RECE"),
            ("预付款项", "PREPAYMENT"),
            ("存货", "INVENTORY"),
            ("营业成本", COGS_FIELDS),
            ("营业收入", REVENUE_FIELDS),
            ("固定资产", "FIXED_ASSET"),
            ("披露毛利率", _pct_col("XSMLL")),
        ],
    )
    rows: list[list[str]] = []
    for row in annual[:PERIOD_LIMIT]:
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
    return _compose_step(
        raw=raw,
        formulas=[
            ("两头吃指数", "(应付账款 + 预收款项/合同负债) ÷ (应收账款 + 预付款项)；>1 表示对上下游占款能力强"),
            ("存货周转天数", "365 × 存货 ÷ 营业成本"),
            ("应收周转天数", "365 × 应收账款 ÷ 营业收入"),
            ("固定资产周转", "营业收入 ÷ 固定资产"),
        ],
        results=md_table(
            ["报告期", "两头吃指数", "存货周转天数", "应收周转天数", "固定资产周转", "毛利率"],
            rows,
        ),
        conclusions=_competitiveness_conclusions(annual),
    )


def _cost_structure_table(annual: list[dict[str, Any]]) -> str:
    raw = _raw_md(
        annual,
        [
            ("营业收入", REVENUE_FIELDS),
            ("营业成本", COGS_FIELDS),
            ("销售费用", "SALE_EXPENSE"),
            ("管理费用", "MANAGE_EXPENSE"),
            ("研发费用", "RESEARCH_EXPENSE"),
            ("财务费用", "FINANCE_EXPENSE"),
            ("披露毛利率", _pct_col("XSMLL")),
        ],
    )
    rows: list[list[str]] = []
    for row in annual[:PERIOD_LIMIT]:
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
    return _compose_step(
        raw=raw,
        formulas=[
            ("营业成本率", "营业成本 ÷ 营业收入"),
            ("销售/管理/研发/财务费用率", "对应期间费用 ÷ 营业收入"),
            ("毛利率", "优先取利润表主要指标；未披露时按 1 − 营业成本率"),
        ],
        results=md_table(
            ["报告期", "营业成本率", "销售费用率", "管理费用率", "研发费用率", "财务费用率", "毛利率"],
            rows,
        ),
        conclusions=_cost_conclusions(annual),
    )


def _dupont_parts(row: dict[str, Any], profit: dict[str, Any]) -> dict[str, Any]:
    assets = _total_assets(row)
    equity = to_float(pick(row, *TOTAL_EQUITY_FIELDS))
    revenue = profit.get("revenue")
    net = profit.get("net_profit")
    roa = to_float(pick(row, "ZZCJLL"))
    if roa is None and net is not None and assets:
        roa = net / assets * 100
    turnover = (revenue / assets) if revenue and assets else None
    multiplier = (assets / equity) if assets and equity else None
    return {
        "roa": roa,
        "asset_turnover": turnover,
        "equity_multiplier": multiplier,
        "equity": equity,
    }


def _value_table(annual: list[dict[str, Any]]) -> str:
    raw = _raw_md(
        annual,
        [
            ("披露ROE", _pct_col("ROEJQ", "WEIGHTAVG_ROE")),
            ("披露ROA", _pct_col("ZZCJLL")),
            ("披露ROIC", _pct_col("ROIC")),
            ("披露净利率", _pct_col("XSJLL")),
            ("营业收入", REVENUE_FIELDS),
            ("归母净利润", NET_PROFIT_FIELDS),
            ("总资产", TOTAL_ASSETS_FIELDS),
            ("净资产", TOTAL_EQUITY_FIELDS),
        ],
    )
    rows: list[list[str]] = []
    for row in annual[:PERIOD_LIMIT]:
        p = _core_profit(row)
        d = _dupont_parts(row, p)
        rows.append(
            [
                period_label(row),
                fmt_pct(p["roe"]),
                fmt_pct(d["roa"]),
                fmt_pct(p["roic"]),
                fmt_pct(p["net_margin"]),
                fmt_x(d["asset_turnover"]),
                fmt_x(d["equity_multiplier"]),
                fmt_yi(p["net_profit"]),
                fmt_yi(d["equity"]),
            ]
        )
    return _compose_step(
        raw=raw,
        formulas=[
            ("ROA", "优先取主要指标总资产净利率；未披露时 归母净利润 ÷ 总资产"),
            ("资产周转", "营业收入 ÷ 总资产"),
            ("权益乘数", "总资产 ÷ 净资产"),
            ("价值创造评价", "ROE ≥15% 优，≥8% 中，否则差"),
        ],
        results=md_table(
            ["报告期", "ROE", "ROA", "ROIC", "净利率", "资产周转", "权益乘数", "归母净利润", "净资产"],
            rows,
        ),
        conclusions=_value_conclusions(annual),
    )


def _snapshot_table(rows: list[dict[str, Any]]) -> str:
    raw = _raw_md(
        rows,
        [
            ("营业收入", REVENUE_FIELDS),
            ("归母净利润", NET_PROFIT_FIELDS),
            ("经营现金流", OCF_FIELDS),
            ("披露ROE", _pct_col("ROEJQ", "WEIGHTAVG_ROE")),
            ("应收账款", "ACCOUNTS_RECE"),
            ("应付账款", "ACCOUNTS_PAYABLE"),
            ("预收/合同负债", ("ADVANCE_RECEIVABLES", "CONTRACT_LIAB")),
            ("预付款项", "PREPAYMENT"),
        ],
        limit=RECENT_LIMIT,
    )
    body: list[list[str]] = []
    for row in rows[:RECENT_LIMIT]:
        p = _core_profit(row)
        c = _competitiveness(row)
        body.append(
            [
                period_label(row),
                period_kind(row),
                fmt_yi(p["revenue"]),
                fmt_yi(p["core_profit"]),
                fmt_pct(p["core_margin"]),
                fmt_yi(_ocf(row)),
                fmt_x(c["two_ends_index"]),
                fmt_pct(p["roe"]),
            ]
        )
    return _compose_step(
        raw=raw,
        formulas=[
            ("核心利润", "营业收入 − 营业成本 − 税金及附加 − 销售/管理/研发/财务费用"),
            ("两头吃指数", "(应付账款 + 预收款项/合同负债) ÷ (应收账款 + 预付款项)"),
            ("覆盖与口径", "按报告日落最新排列；利润表/现金流量表为累计数，不同类型不可直接横比"),
        ],
        results=md_table(
            ["报告期", "类型", "营业收入", "核心利润", "核心利润率", "经营现金流", "两头吃", "ROE"],
            body,
        ),
        conclusions=_snapshot_conclusions(rows),
    )


def _diagnosis_table(metrics: dict[str, Any], flags: list[str]) -> str:
    cash = metrics.get("cash") or {}
    profit = metrics.get("profit") or {}
    strategy = metrics.get("strategy") or {}
    assets = metrics.get("assets") or {}
    comp = metrics.get("competitiveness") or {}
    raw = md_table(
        ["项目", "原始/中间值"],
        [
            ["最新定期报告", f"{metrics.get('latest_period') or '—'}（{metrics.get('period_kind') or '定期报告'}）"],
            ["经营性资产占比", fmt_pct(strategy.get("operating_asset_ratio"))],
            ["投资性资产占比", fmt_pct(strategy.get("investing_asset_ratio"))],
            ["OCF/核心利润", fmt_pct(cash.get("ocf_core_ratio"))],
            ["两头吃指数", fmt_x(comp.get("two_ends_index"))],
            ["ROE", fmt_pct(profit.get("roe"))],
            ["两金", fmt_yi(assets.get("two_gold"))],
            ["警示条数", str(len(flags))],
        ],
    )
    rows = [
        ["战略一致性", strategy.get("strategy_type", "—"), "经营/投资占比及增速"],
        ["利润含金量", _grade(cash.get("ocf_core_ratio"), 100, 80), f"OCF/核心利润 {fmt_pct(cash.get('ocf_core_ratio'))}"],
        ["资产质量", "中" if len(flags) <= 2 else "差", f"警示 {len(flags)} 项"],
        ["竞争力", _grade(comp.get("two_ends_index"), 1.2, 0.8), f"两头吃 {fmt_x(comp.get('two_ends_index'))}"],
        ["价值创造", _grade(profit.get("roe"), 15, 8), f"ROE {fmt_pct(profit.get('roe'))}"],
    ]
    if metrics.get("latest_period"):
        rows.insert(0, ["最新定期报告", metrics["latest_period"], metrics.get("period_kind") or "定期报告"])
    if metrics.get("coverage"):
        rows.insert(1, ["数据覆盖", metrics["coverage"], "年报/半年报/季报均纳入，同比用同口径"])
    return _compose_step(
        raw=raw,
        formulas=[
            ("战略一致性", "投资占比>35%且投资增速>经营增速 → 投资主导；经营占比>65% → 经营主导；否则混合"),
            ("利润含金量", "OCF/核心利润 ≥100% 优，≥80% 中，否则差"),
            ("资产质量", "风险警示 ≤2 项为中，否则差"),
            ("竞争力", "两头吃指数 ≥1.2 优，≥0.8 中，否则差"),
            ("价值创造", "ROE ≥15% 优，≥8% 中，否则差"),
        ],
        results=md_table(["维度", "评价", "关键证据"], rows),
        conclusions=_diagnosis_conclusions(metrics, flags, rows),
    )


def run_zhang_analysis(
    annual: list[dict[str, Any]] | None = None,
    recent: list[dict[str, Any]] | None = None,
    *,
    merged: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """运行张新民「八看」全套规则引擎：默认用最新定期报告，并按同一报告类型回溯。"""
    selected = select_periodic_rows(annual=annual, recent=recent, merged=merged)
    if not selected:
        return {
            "metrics": {},
            "flags": [],
            "tables": {},
            "text": "（未能获取财务报表数据）",
            "strategy_type": "未知",
        }

    kind = period_kind(selected[0])
    ytd = kind != "年报"
    pool = list(merged or recent or annual or selected)
    annual_rows = [row for row in pool if period_kind(row) == "年报"][:PERIOD_LIMIT]
    mixed_rows = pool[:RECENT_LIMIT]

    latest = selected[0]
    prev = selected[1] if len(selected) > 1 else None
    assets = _classify_assets(latest)
    liab = _classify_liabilities(latest)
    profit = _core_profit(latest)
    cash = _cash_quality(latest, prev)
    comp = _competitiveness(latest)
    strategy = _strategy_type(latest, prev)
    flags = _risk_flags(assets, liab, profit, cash, strategy)
    coverage = (
        f"同口径{len(selected)}期{kind}"
        + (f" · 年报{len(annual_rows)}期" if annual_rows else "")
        + f" · 定期报告共{len(pool)}期"
    )
    if ytd:
        flags.insert(
            0,
            f"最新定期报告为{kind}，利润表/现金流量表是累计数，不可与年报直接横比；周转天数按累计数×365估算，会偏高",
        )
        if annual_rows:
            flags.insert(
                1,
                f"多年结构对照另附表年报序列，最近年报为{period_label(annual_rows[0])}",
            )

    metrics: dict[str, Any] = {
        "latest_period": period_label(latest),
        "period_kind": kind,
        "ytd": ytd,
        "coverage": coverage,
        "period_count": len(selected),
        "annual_count": len(annual_rows),
        "merged_count": len(pool),
        "assets": assets,
        "liabilities": liab,
        "profit": profit,
        "cash": cash,
        "competitiveness": comp,
        "strategy": strategy,
    }

    tables = {
        "asset_structure": _asset_structure_table(selected),
        "liability_structure": _liability_structure_table(selected),
        "core_profit": _core_profit_table(selected),
        "cash_quality": _cash_quality_table(selected),
        "competitiveness": _competitiveness_table(selected),
        "cost_structure": _cost_structure_table(selected),
        "value": _value_table(selected),
        "recent_all": _snapshot_table(mixed_rows),
        "diagnosis": _diagnosis_table(metrics, flags),
    }
    if ytd and annual_rows:
        tables["annual_core"] = _core_profit_table(annual_rows)
        tables["annual_value"] = _value_table(annual_rows)

    ytd_note = f"，{kind}累计口径" if ytd else ""
    text_parts = [
        f"### 战略类型：{strategy['strategy_type']}",
        f"- 最新定期报告：{period_label(latest)}（{kind}{ytd_note}）",
        f"- 数据覆盖：{coverage}",
        f"- 经营性资产占比：{fmt_pct(strategy.get('operating_asset_ratio'))}",
        f"- 投资性资产占比：{fmt_pct(strategy.get('investing_asset_ratio'))}",
        f"- 重资产指数（固定资产/总资产）：{fmt_pct(strategy.get('heavy_asset_ratio'))}",
        "",
        f"### 核心利润（{period_label(latest)}）",
        f"- 核心利润：{fmt_yi(profit.get('core_profit'))}，核心利润率 {fmt_pct(profit.get('core_margin'))}，毛利率 {fmt_pct(profit.get('gross_margin'))}",
        f"- 归母净利润：{fmt_yi(profit.get('net_profit'))}，扣非占比 {fmt_pct(profit.get('deduct_ratio'))}",
        "",
        "### 利润含金量",
        f"- 经营现金流/核心利润：{fmt_pct(cash.get('ocf_core_ratio'))}",
        f"- 经营现金流/净利润：{fmt_pct(cash.get('ocf_profit_ratio'))}",
        f"- 销售收现比：{fmt_pct(cash.get('cash_collection_ratio'))}",
        f"- 现金流模式：{cash.get('cashflow_mode')}",
        "",
        "### 竞争力",
        f"- 两头吃指数：{fmt_x(comp.get('two_ends_index'))}＝(应付+预收)÷(应收+预付)（>1 表示对上下游占款能力强）",
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
        "recent_periods": [period_label(r) for r in mixed_rows[:8]],
    }
