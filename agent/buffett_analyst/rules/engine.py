"""巴菲特读表规则引擎：所有者盈余区间、资本饥饿、四种生意分类。"""

from __future__ import annotations

import re
from typing import Any

from agent.buffett_analyst.rules._fields import (
    ACCEPT_INVEST_FIELDS,
    CAPEX_FIELDS,
    CIP_FIELDS,
    DA_FA_IR,
    DA_IA,
    DA_IR,
    DA_LPE,
    DA_OILGAS,
    DEDUCT_PROFIT_FIELDS,
    DIVIDEND_CASH_FIELDS,
    DIVIDEND_DESC_FIELDS,
    DIVIDEND_FIELDS,
    EQUITY_FIELDS,
    FIN_CF_FIELDS,
    FIXED_ASSET_FIELDS,
    GOODWILL_FIELDS,
    INTANGIBLE_FIELDS,
    ISSUE_BOND_FIELDS,
    NET_PROFIT_FIELDS,
    OCF_FIELDS,
    PAY_DEBT_FIELDS,
    RECEIVE_LOAN_FIELDS,
    REVENUE_FIELDS,
    SHARE_CAPITAL_FIELDS,
    TOTAL_SHARE_FIELDS,
    TOTAL_ASSETS_FIELDS,
)
from agent.comprehensive_analyst.rules._common import (
    fmt_pct,
    fmt_x,
    fmt_yi,
    md_table,
    period_label,
    pick,
    to_float,
)


HIGH_ROE = 15.0
MID_ROE = 8.0
LOW_CAPEX_DA = 1.3
HIGH_CAPEX_DA = 1.8
PERIOD_LIMIT = 8
RECENT_LIMIT = 12


def _with_formulas(table: str, formulas: list[tuple[str, str]]) -> str:
    if not table or not formulas:
        return table
    return (
        table
        + "\n\n**计算公式**\n\n"
        + md_table(["指标", "计算公式"], [[name, formula] for name, formula in formulas])
    )


def _cell(value: Any, *, undisclosed: bool = False, kind: str = "yi") -> str:
    if undisclosed:
        return "未披露"
    if value is None:
        return "—"
    if kind == "pct":
        return fmt_pct(value)
    if kind == "x":
        return fmt_x(value)
    return fmt_yi(value)


def _revenue(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *REVENUE_FIELDS))


def _net_profit(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *NET_PROFIT_FIELDS))


def _deduct_profit(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *DEDUCT_PROFIT_FIELDS))


def _ocf(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *OCF_FIELDS))


def _capex_outflow(row: dict[str, Any]) -> float | None:
    raw = to_float(pick(row, *CAPEX_FIELDS))
    if raw is None:
        return None
    return abs(raw)


def _equity(row: dict[str, Any]) -> float | None:
    return to_float(pick(row, *EQUITY_FIELDS))


def _da_and_amort(row: dict[str, Any]) -> tuple[float | None, bool]:
    """折旧摊销合计 (b)。全部缺列时返回 (None, False)。"""
    fa_ir = to_float(pick(row, DA_FA_IR))
    oil = to_float(pick(row, DA_OILGAS))
    ir = to_float(pick(row, DA_IR))
    ia = to_float(pick(row, DA_IA))
    lpe = to_float(pick(row, DA_LPE))
    present = [fa_ir, oil, ir, ia, lpe]
    if all(item is None for item in present):
        return None, False
    depr = fa_ir
    if depr is None and (oil is not None or ir is not None):
        depr = (oil or 0.0) + (ir or 0.0)
    total = (depr or 0.0) + (ia or 0.0) + (lpe or 0.0)
    return total, True


def _ppe(row: dict[str, Any]) -> float | None:
    fixed = to_float(pick(row, *FIXED_ASSET_FIELDS))
    cip = to_float(pick(row, *CIP_FIELDS))
    if fixed is None and cip is None:
        return None
    return (fixed or 0.0) + (cip or 0.0)


def _working_capital(row: dict[str, Any]) -> float:
    recv = to_float(pick(row, "ACCOUNTS_RECE")) or 0.0
    inv = to_float(pick(row, "INVENTORY")) or 0.0
    prepay = to_float(pick(row, "PREPAYMENT")) or 0.0
    payable = to_float(pick(row, "ACCOUNTS_PAYABLE")) or 0.0
    advance = to_float(pick(row, "ADVANCE_RECEIVABLES", "CONTRACT_LIAB")) or 0.0
    return recv + inv + prepay - payable - advance


def _tangible_equity(row: dict[str, Any]) -> float | None:
    equity = _equity(row)
    if equity is None:
        return None
    goodwill = to_float(pick(row, *GOODWILL_FIELDS)) or 0.0
    intangible = to_float(pick(row, *INTANGIBLE_FIELDS)) or 0.0
    return equity - goodwill - intangible


def _gross_margin(row: dict[str, Any]) -> float | None:
    disclosed = to_float(pick(row, "XSMLL"))
    if disclosed is not None:
        return disclosed
    revenue = _revenue(row)
    cogs = to_float(pick(row, "OPERATE_COST", "OPERATE_EXPENSE"))
    if revenue and cogs is not None:
        return (revenue - cogs) / revenue * 100
    return None


_NO_DIVIDEND_MARKERS = ("不分配", "不分红", "不派息", "不派发现金", "不进行利润分配")
_ASSIGN_CASH_RE = re.compile(
    r"(?:每)?(?P<base>\d+(?:\.\d+)?)\s*(?:股)?"
    r"(?:转(?:增)?\s*\d+(?:\.\d+)?)?"
    r"(?:送\s*\d+(?:\.\d+)?)?"
    r"派(?:发现金股利|现金股利)?"
    r"(?P<cash>\d+(?:\.\d+)?)\s*元",
)


def _assign_desc(row: dict[str, Any]) -> str:
    raw = pick(row, *DIVIDEND_DESC_FIELDS)
    return str(raw).strip() if raw is not None else ""


def _proposed_cash_dividend(row: dict[str, Any]) -> float | None:
    """拟派现金股利总额。东财 ASSIGN_CASH_DIVIDEND 对 A 股经常为空，改从利润分配说明估算。"""
    direct = to_float(pick(row, *DIVIDEND_FIELDS))
    if direct is not None:
        return direct
    desc = re.sub(r"\s+", "", _assign_desc(row))
    if not desc:
        return None
    if any(marker in desc for marker in _NO_DIVIDEND_MARKERS):
        return 0.0
    match = _ASSIGN_CASH_RE.search(desc)
    if not match:
        return None
    base = to_float(match.group("base"))
    cash = to_float(match.group("cash"))
    shares = to_float(pick(row, *TOTAL_SHARE_FIELDS))
    if not base or cash is None or shares is None:
        return None
    return shares * (cash / base)


def _period_metrics(row: dict[str, Any]) -> dict[str, Any]:
    a = _net_profit(row)
    deduct = _deduct_profit(row)
    b, da_ok = _da_and_amort(row)
    capex = _capex_outflow(row)
    ocf = _ocf(row)
    revenue = _revenue(row)
    equity = _equity(row)
    tangible = _tangible_equity(row)
    ppe = _ppe(row)
    wc = _working_capital(row)
    goodwill = to_float(pick(row, *GOODWILL_FIELDS))
    intangible = to_float(pick(row, *INTANGIBLE_FIELDS))
    total_assets = to_float(pick(row, *TOTAL_ASSETS_FIELDS))
    roe = to_float(pick(row, "ROEJQ", "WEIGHTAVG_ROE"))
    if roe is None and a is not None and equity:
        roe = a / equity * 100
    tangible_roe = None
    if a is not None and tangible:
        tangible_roe = a / tangible * 100

    oe_upper = a if a is not None else None
    oe_lower = None
    if a is not None and da_ok and b is not None and capex is not None:
        oe_lower = a + b - capex
    fcf = None
    if ocf is not None:
        fcf = ocf - (capex or 0.0)
    capex_da = None
    if da_ok and b and b != 0 and capex is not None:
        capex_da = capex / b
    ocf_ni = None
    if ocf is not None and a:
        ocf_ni = ocf / a * 100
    deduct_ratio = None
    if deduct is not None and a:
        deduct_ratio = deduct / a * 100
    ppe_sales = None
    if ppe is not None and revenue:
        ppe_sales = ppe / revenue * 100

    return {
        "period": period_label(row),
        "a": a,
        "deduct": deduct,
        "b": b,
        "da_disclosed": da_ok,
        "capex": capex,
        "oe_upper": oe_upper,
        "oe_lower": oe_lower,
        "ocf": ocf,
        "fcf": fcf,
        "ocf_ni": ocf_ni,
        "capex_da": capex_da,
        "revenue": revenue,
        "equity": equity,
        "tangible_equity": tangible,
        "tangible_roe": tangible_roe,
        "roe": roe,
        "ppe": ppe,
        "wc": wc,
        "goodwill": goodwill,
        "intangible": intangible,
        "total_assets": total_assets,
        "gross_margin": _gross_margin(row),
        "deduct_ratio": deduct_ratio,
        "ppe_sales": ppe_sales,
        "dividend": _proposed_cash_dividend(row),
        "dividend_cash": to_float(pick(row, *DIVIDEND_CASH_FIELDS)),
        "share_capital": to_float(pick(row, *SHARE_CAPITAL_FIELDS)),
        "accept_invest": to_float(pick(row, *ACCEPT_INVEST_FIELDS)),
        "issue_bond": to_float(pick(row, *ISSUE_BOND_FIELDS)),
        "receive_loan": to_float(pick(row, *RECEIVE_LOAN_FIELDS)),
        "pay_debt": to_float(pick(row, *PAY_DEBT_FIELDS)),
        "fin_cf": to_float(pick(row, *FIN_CF_FIELDS)),
    }


def _mean(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _incremental_return(periods: list[dict[str, Any]]) -> dict[str, Any]:
    if len(periods) < 2:
        return {
            "delta_ni": None,
            "delta_capital": None,
            "incremental_return": None,
            "negative_capital_positive_profit": False,
        }
    newest, oldest = periods[0], periods[-1]
    ni_n, ni_o = newest.get("a"), oldest.get("a")
    ppe_n, ppe_o = newest.get("ppe"), oldest.get("ppe")
    wc_n, wc_o = newest.get("wc") or 0.0, oldest.get("wc") or 0.0
    delta_ni = (ni_n - ni_o) if ni_n is not None and ni_o is not None else None
    if ppe_n is None or ppe_o is None:
        delta_capital = None
    else:
        delta_capital = (ppe_n + wc_n) - (ppe_o + wc_o)
    incremental = None
    negative_cap = False
    if delta_ni is not None and delta_capital is not None:
        if delta_capital > 0:
            incremental = delta_ni / delta_capital * 100
        elif delta_capital <= 0 and delta_ni > 0:
            negative_cap = True
    return {
        "delta_ni": delta_ni,
        "delta_capital": delta_capital,
        "incremental_return": incremental,
        "negative_capital_positive_profit": negative_cap,
        "from_period": oldest.get("period"),
        "to_period": newest.get("period"),
    }


def _dollar_test(periods: list[dict[str, Any]]) -> dict[str, Any]:
    if len(periods) < 2:
        return {
            "cum_ni": None,
            "delta_equity": None,
            "cum_dividend": None,
            "retained": None,
            "share_dilution": False,
            "accept_invest_sum": None,
        }
    newest, oldest = periods[0], periods[-1]
    inner = periods[:-1]
    cum_ni = None
    ni_vals = [p.get("a") for p in inner]
    if all(v is not None for v in ni_vals) and ni_vals:
        cum_ni = sum(ni_vals)
    eq_n, eq_o = newest.get("equity"), oldest.get("equity")
    delta_equity = (eq_n - eq_o) if eq_n is not None and eq_o is not None else None
    div_vals = [p.get("dividend") for p in inner]
    cum_div = None
    if any(v is not None for v in div_vals):
        cum_div = sum(v or 0.0 for v in div_vals)
    retained = None
    if cum_ni is not None:
        retained = cum_ni - (cum_div or 0.0)
    share_n = newest.get("share_capital")
    share_o = oldest.get("share_capital")
    dilution = bool(share_n is not None and share_o is not None and share_n > share_o * 1.05)
    accept = sum((p.get("accept_invest") or 0.0) for p in inner)
    return {
        "cum_ni": cum_ni,
        "delta_equity": delta_equity,
        "cum_dividend": cum_div,
        "retained": retained,
        "share_dilution": dilution,
        "accept_invest_sum": accept if accept else None,
        "from_period": oldest.get("period"),
        "to_period": newest.get("period"),
    }


def _classify_business(
    latest: dict[str, Any],
    avg_roe: float | None,
    avg_capex_da: float | None,
    incremental: dict[str, Any],
) -> tuple[str, str]:
    """返回 (类型, 依据)。LLM 不得改写类型。"""
    roe = avg_roe if avg_roe is not None else latest.get("tangible_roe") or latest.get("roe")
    capex_da = avg_capex_da if avg_capex_da is not None else latest.get("capex_da")
    expanding = bool(
        (latest.get("capex") or 0) > 0
        and (
            (latest.get("ppe_sales") or 0) > 20
            or (capex_da is not None and capex_da > LOW_CAPEX_DA)
        )
    )
    incr = incremental.get("incremental_return")
    neg_cap = incremental.get("negative_capital_positive_profit")

    if roe is None:
        return "数据不足", "有形 ROE / 报告 ROE 均未算出，无法分类"

    light = capex_da is not None and capex_da <= LOW_CAPEX_DA
    light_proxy = capex_da is None and (latest.get("ppe_sales") or 0) <= 25
    if roe >= HIGH_ROE and (neg_cap or light or light_proxy):
        return "伟大", f"高回报（ROE {fmt_pct(roe)}）且资本饥饿低（capex/D&A {fmt_x(capex_da)}）"
    if roe >= HIGH_ROE and capex_da is not None and capex_da > LOW_CAPEX_DA:
        if incr is None or incr >= HIGH_ROE or neg_cap:
            return "优秀", f"高回报（ROE {fmt_pct(roe)}）且能消化大额再投入（capex/D&A {fmt_x(capex_da)}）"
        return "平庸", f"回报高但增量资本回报一般（增量回报 {fmt_pct(incr)}，capex/D&A {fmt_x(capex_da)}）"
    if roe >= HIGH_ROE and capex_da is None:
        return "优秀", f"高回报（ROE {fmt_pct(roe)}）但折旧未披露，固定资产占营收 {fmt_pct(latest.get('ppe_sales'))}，不能按喜诗处理"
    if roe < MID_ROE and expanding:
        return "糟糕", f"低回报（ROE {fmt_pct(roe)}）仍在扩张，资本消耗可能让所有者变穷"
    if roe >= MID_ROE:
        return "平庸", f"中等回报（ROE {fmt_pct(roe)}），资本开支强度 {fmt_x(capex_da)}"
    return "平庸", f"回报偏低（ROE {fmt_pct(roe)}），但未见明显扩张式消耗"


def _risk_flags(
    latest: dict[str, Any],
    dollar: dict[str, Any],
    business_type: str,
) -> list[str]:
    flags: list[str] = []
    if not latest.get("da_disclosed"):
        flags.append("折旧摊销附注未披露，所有者盈余下沿失效，只能把上沿近似为报告盈利")
    if latest.get("ocf_ni") is not None and latest["ocf_ni"] < 80:
        flags.append(f"经营现金流/净利润偏低：{fmt_pct(latest['ocf_ni'])}")
    if latest.get("ocf") is not None and latest["ocf"] < 0:
        flags.append("经营现金流为负，利润没有现金支撑")
    gw = latest.get("goodwill") or 0.0
    assets = latest.get("total_assets") or 0.0
    if gw and assets and gw / assets > 0.15:
        flags.append(f"商誉占总资产 {fmt_pct(gw / assets * 100)}，会计商誉与经济特许权需分开看")
    if latest.get("deduct_ratio") is not None and latest["deduct_ratio"] < 70:
        flags.append(f"扣非占归母净利润 {fmt_pct(latest['deduct_ratio'])}，报告盈利含较多非经常项目")
    if dollar.get("share_dilution"):
        flags.append("股本明显增加，留存收益的 1 美元测试需扣掉发股")
    if dollar.get("accept_invest_sum"):
        flags.append(f"期间吸收投资现金 {fmt_yi(dollar['accept_invest_sum'])}，存在外部注资/发股痕迹")
    ppe_sales = latest.get("ppe_sales")
    gm = latest.get("gross_margin")
    if ppe_sales is not None and ppe_sales > 40 and gm is not None and gm < 25:
        flags.append(
            f"固定资产占营收 {fmt_pct(ppe_sales)} 且毛利率 {fmt_pct(gm)}，账面盈利可能是受限盈利"
        )
    if business_type == "糟糕":
        flags.append("规则引擎将生意类型标为「糟糕」：低回报叠加资本消耗")
    return flags


def _owner_earnings_table(periods: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for p in periods:
        rows.append(
            [
                p["period"],
                _cell(p["a"]),
                _cell(p["deduct"]),
                _cell(p["b"], undisclosed=not p["da_disclosed"]),
                _cell(p["capex"]),
                _cell(p["oe_upper"]),
                _cell(p["oe_lower"], undisclosed=not p["da_disclosed"] or p["oe_lower"] is None),
                _cell(p["ocf"]),
                _cell(p["fcf"]),
            ]
        )
    return _with_formulas(
        md_table(
            [
                "报告期",
                "(a)归母净利润",
                "扣非净利润",
                "(b)折旧摊销",
                "资本开支",
                "所有者盈余上沿",
                "所有者盈余下沿",
                "经营现金流",
                "OCF−资本开支",
            ],
            rows,
        ),
        [
            ("(a)", "归母净利润；扣非净利润仅作对照，不替代 (a)"),
            ("(b)", "FA_IR_DEPR（或油气/投资性房地产折旧）+ 无形资产摊销 + 长期待摊摊销"),
            ("资本开支", "购建固定资产等现金流出的绝对值，作为 (c) 的保守锚"),
            ("所有者盈余上沿", "(a)+(b)−(b)，即假设维持性投入≈折旧摊销，约等于报告盈利"),
            ("所有者盈余下沿", "(a)+(b)−资本开支；折旧未披露时标「未披露」"),
            ("OCF−资本开支", "自由现金流旁路核对，不是 1986 年所有者盈余公式"),
        ],
    )


def _capital_table(periods: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for p in periods:
        rows.append(
            [
                p["period"],
                _cell(p["roe"], kind="pct"),
                _cell(p["tangible_roe"], kind="pct"),
                _cell(p["tangible_equity"]),
                _cell(p["ppe"]),
                _cell(p["ppe_sales"], kind="pct"),
                _cell(p["capex_da"], undisclosed=not p["da_disclosed"], kind="x"),
                _cell(p["ocf_ni"], kind="pct"),
                _cell(p["gross_margin"], kind="pct"),
            ]
        )
    return _with_formulas(
        md_table(
            [
                "报告期",
                "ROE",
                "有形ROE",
                "有形净资产",
                "固定资产+在建",
                "PPE/营收",
                "capex/D&A",
                "OCF/净利润",
                "毛利率",
            ],
            rows,
        ),
        [
            ("有形净资产", "净资产 − 商誉 − 无形资产"),
            ("有形ROE", "归母净利润 ÷ 有形净资产"),
            ("PPE/营收", "(固定资产+在建工程) ÷ 营业收入"),
            ("capex/D&A", "资本开支 ÷ 折旧摊销；接近 1 且高回报偏喜诗，长期远大于 1 且低回报为资本饥饿"),
            ("OCF/净利润", "经营现金流 ÷ 归母净利润"),
        ],
    )


def _allocation_table(periods: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for p in periods:
        rows.append(
            [
                p["period"],
                _cell(p["dividend"]),
                _cell(p["dividend_cash"]),
                _cell(p["accept_invest"]),
                _cell(p["share_capital"]),
                _cell(p["receive_loan"]),
                _cell(p["issue_bond"]),
                _cell(p["pay_debt"]),
                _cell(p["fin_cf"]),
                _cell(p["goodwill"]),
                _cell(p["deduct_ratio"], kind="pct"),
            ]
        )
    return _with_formulas(
        md_table(
            [
                "报告期",
                "拟派现金股利",
                "分配股利或偿息",
                "吸收投资现金",
                "股本",
                "取得借款",
                "发行债券",
                "偿还债务",
                "筹资现金流",
                "商誉",
                "扣非占比",
            ],
            rows,
        ),
        [
            ("拟派现金股利", "优先 ASSIGN_CASH_DIVIDEND；为空则从利润分配说明 ASSIGNDSCRPT（如 10派xx元）×总股本估算；不分配记 0"),
            ("分配股利或偿息", "筹资活动 ASSIGN_DIVIDEND_PORFIT，含偿付利息，不能当成纯分红"),
            ("吸收投资现金", "ACCEPT_INVEST_CASH，用来识别发股/注资"),
            ("扣非占比", "扣非净利润 ÷ 归母净利润"),
        ],
    )


def _snapshot_table(periods: list[dict[str, Any]]) -> str:
    rows: list[list[str]] = []
    for p in periods:
        rows.append(
            [
                p["period"],
                p.get("period_kind") or "",
                _cell(p["a"]),
                _cell(p["ocf"]),
                _cell(p["capex"]),
                _cell(p["tangible_roe"] or p.get("roe"), kind="pct"),
                _cell(p["oe_upper"]),
                _cell(p["oe_lower"], undisclosed=not p.get("da_disclosed") or p.get("oe_lower") is None),
            ]
        )
    return _with_formulas(
        md_table(
            [
                "报告期",
                "类型",
                "归母净利润",
                "经营现金流",
                "资本开支",
                "有形ROE",
                "所有者盈余上沿",
                "所有者盈余下沿",
            ],
            rows,
        ),
        [
            ("覆盖", "按报告日落最新的定期报告，年报/半年报/季报都列入"),
            ("有形ROE", "归母净利润 ÷ 有形净资产；季报为累计口径"),
        ],
    )


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
    latest = pool[0]
    kind = period_kind(latest)
    same = [row for row in pool if period_kind(row) == kind]
    if same:
        return same[:limit]
    return pool[:limit]


def _diagnosis_table(
    business_type: str,
    reason: str,
    latest: dict[str, Any],
    incremental: dict[str, Any],
    dollar: dict[str, Any],
) -> str:
    rows = [
        ["生意类型（规则引擎，禁止改写）", business_type, reason],
        ["所有者盈余上沿", _cell(latest.get("oe_upper")), "假设维持性投入≈折旧"],
        [
            "所有者盈余下沿",
            _cell(latest.get("oe_lower"), undisclosed=not latest.get("da_disclosed")),
            "把当年资本开支全当维持",
        ],
        ["OCF−资本开支", _cell(latest.get("fcf")), "旁路核对，非同一公式"],
        [
            "增量资本回报",
            "负增量资本仍增利" if incremental.get("negative_capital_positive_profit") else _cell(incremental.get("incremental_return"), kind="pct"),
            f"{incremental.get('from_period') or '—'} → {incremental.get('to_period') or '—'}",
        ],
        [
            "留存 vs Δ净资产",
            f"留存 {_cell(dollar.get('retained'))} / Δ净资产 {_cell(dollar.get('delta_equity'))}",
            "分红缺省时留存=累计净利润",
        ],
    ]
    if latest.get("period_kind"):
        rows.insert(1, ["最新定期报告", latest.get("period") or "—", latest.get("period_kind") or "定期报告"])
    coverage = latest.get("coverage")
    if coverage:
        rows.insert(2, ["数据覆盖", coverage, "强制刷新东财 F10 全量定期报告后计算"])
    return md_table(["维度", "结论", "证据"], rows)


def run_buffett_analysis(
    annual: list[dict[str, Any]] | None = None,
    recent: list[dict[str, Any]] | None = None,
    *,
    merged: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """运行巴菲特读表规则引擎：默认用最新定期报告，并按同一报告类型回溯。"""
    selected = select_periodic_rows(annual=annual, recent=recent, merged=merged)
    if not selected:
        return {
            "metrics": {},
            "flags": [],
            "tables": {},
            "text": "（未能获取财务报表数据）",
            "business_type": "未知",
        }

    kind = period_kind(selected[0])
    ytd = kind != "年报"
    pool = list(merged or recent or annual or selected)
    annual_rows = [row for row in pool if period_kind(row) == "年报"][:PERIOD_LIMIT]
    mixed_rows = pool[:RECENT_LIMIT]

    def _metrics_for(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for row in rows:
            item = _period_metrics(row)
            item["period_kind"] = period_kind(row)
            out.append(item)
        return out

    periods = _metrics_for(selected)
    annual_periods = _metrics_for(annual_rows)
    mixed_periods = _metrics_for(mixed_rows)
    latest = periods[0]
    latest["period_kind"] = kind
    latest["ytd"] = ytd
    trend = annual_periods if (ytd and len(annual_periods) >= 2) else periods
    window = trend[: min(5, len(trend))]
    avg_roe = _mean([p.get("tangible_roe") or p.get("roe") for p in window])
    avg_capex_da = _mean([p.get("capex_da") for p in window])
    incremental = _incremental_return(trend)
    dollar = _dollar_test(trend)
    business_type, reason = _classify_business(latest, avg_roe, avg_capex_da, incremental)
    flags = _risk_flags(latest, dollar, business_type)
    coverage = (
        f"同口径{len(periods)}期{kind}"
        + (f" · 年报{len(annual_periods)}期" if annual_periods else "")
        + f" · 定期报告共{len(pool)}期"
    )
    latest["coverage"] = coverage
    if ytd:
        flags.insert(
            0,
            f"最新定期报告为{kind}，利润表/现金流量表是累计数，不可与年报直接横比",
        )
        if annual_periods:
            flags.insert(
                1,
                f"多年趋势（平均回报、留存1美元、增量资本）改用年报序列，最近年报为{annual_periods[0]['period']}",
            )

    metrics: dict[str, Any] = {
        "latest_period": latest["period"],
        "period_kind": kind,
        "ytd": ytd,
        "coverage": coverage,
        "period_count": len(periods),
        "annual_count": len(annual_periods),
        "merged_count": len(pool),
        "latest": latest,
        "periods": periods,
        "annual_periods": annual_periods,
        "avg_roe": avg_roe,
        "avg_capex_da": avg_capex_da,
        "incremental": incremental,
        "dollar": dollar,
        "business_type": business_type,
        "business_reason": reason,
    }

    tables = {
        "owner_earnings": _owner_earnings_table(periods),
        "capital": _capital_table(periods),
        "allocation": _allocation_table(periods),
        "diagnosis": _diagnosis_table(business_type, reason, latest, incremental, dollar),
        "recent_all": _snapshot_table(mixed_periods),
    }
    if ytd and annual_periods:
        tables["annual_owner"] = _owner_earnings_table(annual_periods)

    da_note = (
        f"{fmt_yi(latest.get('b'))}"
        if latest.get("da_disclosed")
        else "未披露"
    )
    ytd_note = f"，{kind}累计口径" if ytd else ""
    avg_window = f"近{len(window)}期{'年报' if trend is annual_periods else '同口径'}"
    text_parts = [
        f"### 生意类型：{business_type}",
        f"- 分类依据：{reason}",
        f"- 最新定期报告：{latest['period']}（{kind}{ytd_note}）",
        f"- 数据覆盖：{coverage}",
        "",
        f"### 所有者盈余（{latest['period']}）",
        f"- (a) 归母净利润：{fmt_yi(latest.get('a'))}，扣非：{fmt_yi(latest.get('deduct'))}",
        f"- (b) 折旧摊销：{da_note}",
        f"- 资本开支（(c) 保守锚）：{fmt_yi(latest.get('capex'))}",
        f"- 所有者盈余上沿：{fmt_yi(latest.get('oe_upper'))}",
        f"- 所有者盈余下沿：{_cell(latest.get('oe_lower'), undisclosed=not latest.get('da_disclosed'))}",
        f"- OCF−资本开支（旁路）：{fmt_yi(latest.get('fcf'))}",
        f"- OCF/净利润：{fmt_pct(latest.get('ocf_ni'))}",
        "",
        "### 资本与回报",
        f"- ROE：{fmt_pct(latest.get('roe'))}，有形ROE：{fmt_pct(latest.get('tangible_roe'))}，{avg_window}均ROE：{fmt_pct(avg_roe)}",
        f"- capex/D&A：{fmt_x(latest.get('capex_da'))}，{avg_window}均：{fmt_x(avg_capex_da)}",
        f"- PPE/营收：{fmt_pct(latest.get('ppe_sales'))}，毛利率：{fmt_pct(latest.get('gross_margin'))}",
        (
            "- 增量资本回报：负增量资本仍增利"
            if incremental.get("negative_capital_positive_profit")
            else f"- 增量资本回报：{fmt_pct(incremental.get('incremental_return'))}"
            f"（{incremental.get('from_period') or '—'} → {incremental.get('to_period') or '—'}）"
        ),
        "",
        "### 留存 1 美元测试（近似）",
        f"- 累计利润：{fmt_yi(dollar.get('cum_ni'))}，累计股利（若有）：{fmt_yi(dollar.get('cum_dividend'))}",
        f"- 近似留存：{fmt_yi(dollar.get('retained'))}，Δ净资产：{fmt_yi(dollar.get('delta_equity'))}",
        f"- 发股稀释：{'是' if dollar.get('share_dilution') else '未见明显稀释'}",
        "",
        "### 风险警示",
    ]
    if flags:
        text_parts.extend(f"- {item}" for item in flags)
    else:
        text_parts.append("- 暂无重大警示")

    return {
        "metrics": metrics,
        "flags": flags,
        "tables": tables,
        "text": "\n".join(text_parts),
        "business_type": business_type,
        "recent_periods": [p["period"] for p in mixed_periods],
    }
