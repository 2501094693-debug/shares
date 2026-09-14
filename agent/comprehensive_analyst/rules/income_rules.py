"""利润表规则引擎。"""

from __future__ import annotations

from typing import Any

from agent.comprehensive_analyst.rules._common import (
    fmt_num,
    fmt_pct,
    fmt_yi,
    md_table,
    period_label,
    pick,
    to_float,
    yoy,
)


def _revenue(row: dict[str, Any]) -> Any:
    return pick(row, "TOTALOPERATEREVE", "TOTAL_OPERATE_INCOME", "OPERATE_INCOME_PK")


def _net_profit(row: dict[str, Any]) -> Any:
    return pick(row, "PARENTNETPROFIT", "PARENT_NETPROFIT")


def _op_profit(row: dict[str, Any]) -> Any:
    return pick(row, "OPERATE_PROFIT_PK", "OPERATE_PROFIT")


def analyze_income_statement(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """分析利润表，返回指标表、警示与 Markdown 摘要。"""
    if not rows:
        return {"text": "（未能获取利润表数据）", "flags": [], "metrics": {}}

    annual = rows[:5]
    latest = annual[0]
    prev = annual[1] if len(annual) > 1 else {}

    flags: list[str] = []
    metrics: dict[str, Any] = {}

    rev = to_float(_revenue(latest))
    rev_prev = to_float(_revenue(prev))
    profit = to_float(_net_profit(latest))
    profit_prev = to_float(_net_profit(prev))
    gross_margin = to_float(pick(latest, "XSMLL"))
    net_margin = to_float(pick(latest, "XSJLL"))
    roe = to_float(pick(latest, "ROEJQ", "WEIGHTAVG_ROE"))
    roic = to_float(pick(latest, "ROIC"))
    deduct = to_float(pick(latest, "KCFJCXSYJLR", "DEDUCT_PARENT_NETPROFIT"))

    rev_yoy = yoy(rev, rev_prev)
    profit_yoy = yoy(profit, profit_prev)

    metrics.update(
        {
            "revenue": rev,
            "net_profit": profit,
            "gross_margin": gross_margin,
            "net_margin": net_margin,
            "roe": roe,
            "roic": roic,
            "rev_yoy": rev_yoy,
            "profit_yoy": profit_yoy,
        }
    )

    if rev_yoy is not None and rev_yoy < 0:
        flags.append(f"营收同比下滑 {fmt_pct(rev_yoy)}")
    if profit_yoy is not None and profit_yoy < -20:
        flags.append(f"归母净利润同比下滑 {fmt_pct(profit_yoy)}")
    if profit and deduct and abs(profit - deduct) / max(abs(profit), 1) > 0.3:
        flags.append("扣非净利润与归母净利润差距较大，利润质量需关注")
    if gross_margin is not None and gross_margin < 15:
        flags.append(f"毛利率偏低：{fmt_pct(gross_margin)}")
    if roe is not None and roe < 8:
        flags.append(f"ROE 偏低：{fmt_pct(roe)}")

    trend_rows: list[list[str]] = []
    for row in annual:
        trend_rows.append(
            [
                period_label(row),
                fmt_yi(_revenue(row)),
                fmt_pct(pick(row, "TOTALOPERATEREVETZ", "TOI_RATIO")),
                fmt_yi(_op_profit(row)),
                fmt_yi(_net_profit(row)),
                fmt_pct(pick(row, "PARENTNETPROFITTZ", "PARENT_NETPROFIT_RATIO")),
                fmt_pct(pick(row, "XSMLL")),
                fmt_pct(pick(row, "XSJLL")),
                fmt_pct(pick(row, "ROEJQ", "WEIGHTAVG_ROE")),
                fmt_num(pick(row, "EPSJB", "BASIC_EPS"), 3),
            ]
        )

    expense_rows: list[list[str]] = []
    for row in annual[:3]:
        rev_v = to_float(_revenue(row))
        if not rev_v:
            continue
        expense_rows.append(
            [
                period_label(row),
                fmt_pct(to_float(pick(row, "SALE_EXPENSE")) / rev_v * 100 if pick(row, "SALE_EXPENSE") else None),
                fmt_pct(to_float(pick(row, "MANAGE_EXPENSE")) / rev_v * 100 if pick(row, "MANAGE_EXPENSE") else None),
                fmt_pct(to_float(pick(row, "FINANCE_EXPENSE")) / rev_v * 100 if pick(row, "FINANCE_EXPENSE") else None),
                fmt_pct(to_float(pick(row, "RESEARCH_EXPENSE", "RD_EXPENSE")) / rev_v * 100
                        if pick(row, "RESEARCH_EXPENSE", "RD_EXPENSE") else None),
            ]
        )

    flag_text = "\n".join(f"- ⚠ {f}" for f in flags) if flags else "- 未发现显著异常警示"
    text = (
        "### 利润表趋势（年报）\n"
        + md_table(
            ["报告期", "营收", "营收同比", "营业利润", "归母净利润", "净利同比", "毛利率", "净利率", "ROE", "EPS"],
            trend_rows,
        )
        + "\n\n### 费用率（占营收）\n"
        + md_table(["报告期", "销售费用率", "管理费用率", "财务费用率", "研发费用率"], expense_rows)
        + f"\n\n### 规则引擎警示\n{flag_text}"
    )

    return {"text": text, "flags": flags, "metrics": metrics}
