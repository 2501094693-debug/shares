"""现金流量表规则引擎。"""

from __future__ import annotations

from typing import Any

from agent.comprehensive_analyst.rules._common import (
    fmt_pct,
    fmt_yi,
    md_table,
    period_label,
    pick,
    to_float,
)


def _ocf(row: dict[str, Any]) -> Any:
    return pick(row, "NETCASH_OPERATE_PK", "NETCASH_OPERATE")


def _capex(row: dict[str, Any]) -> Any:
    return pick(row, "CONSTRUCT_LONG_ASSET")


def _net_profit(row: dict[str, Any]) -> Any:
    return pick(row, "PARENTNETPROFIT", "PARENT_NETPROFIT")


def _fcf(row: dict[str, Any]) -> float | None:
    direct = to_float(pick(row, "FCFF_BACK", "FCFF_FORWARD"))
    if direct is not None:
        return direct
    ocf = to_float(_ocf(row))
    capex = to_float(_capex(row))
    if ocf is None:
        return None
    if capex is None:
        return ocf
    return ocf - capex


def _cashflow_type(ocf: float | None, icf: float | None, fcf_fin: float | None) -> str:
    if ocf is None:
        return "未知"
    if ocf > 0 and (icf is None or icf < 0):
        return "经营型（彼得·林奇）"
    if ocf and ocf < 0 and icf and icf > 0:
        return "投资扩张型"
    if fcf_fin and fcf_fin > 0 and (ocf is None or ocf < 0):
        return "融资型"
    return "混合型"


def analyze_cashflow_statement(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """分析现金流量表，返回指标表、警示与 Markdown 摘要。"""
    if not rows:
        return {"text": "（未能获取现金流量表数据）", "flags": [], "metrics": {}}

    annual = rows[:5]
    latest = annual[0]

    flags: list[str] = []
    metrics: dict[str, Any] = {}

    ocf = to_float(_ocf(latest))
    profit = to_float(_net_profit(latest))
    capex = to_float(_capex(latest))
    icf = to_float(pick(latest, "NETCASH_INVEST_PK", "NETCASH_INVEST"))
    fin_cf = to_float(pick(latest, "NETCASH_FINANCE_PK", "NETCASH_FINANCE"))
    fcf = _fcf(latest)

    ocf_ratio = (ocf / profit * 100) if ocf is not None and profit else None
    metrics.update({"ocf": ocf, "fcf": fcf, "capex": capex, "ocf_ratio": ocf_ratio})

    if profit and profit > 0 and ocf is not None and ocf < profit * 0.5:
        flags.append("经营现金流显著低于净利润，利润含金量偏低")
    if ocf is not None and ocf < 0:
        flags.append("经营现金流为负，需关注主业造血能力")
    if fcf is not None and fcf < 0 and capex and capex > 0:
        flags.append("自由现金流为负，公司处于扩张/投资期")

    trend_rows: list[list[str]] = []
    for row in annual:
        ocf_v = to_float(_ocf(row))
        profit_v = to_float(_net_profit(row))
        ratio = (ocf_v / profit_v * 100) if ocf_v is not None and profit_v else None
        fcf_v = _fcf(row)
        trend_rows.append(
            [
                period_label(row),
                fmt_yi(ocf_v),
                fmt_yi(_capex(row)),
                fmt_yi(fcf_v),
                fmt_pct(ratio) if ratio is not None else "—",
                fmt_yi(pick(row, "NETCASH_INVEST_PK", "NETCASH_INVEST")),
                fmt_yi(pick(row, "NETCASH_FINANCE_PK", "NETCASH_FINANCE")),
            ]
        )

    cf_type = _cashflow_type(ocf, icf, fin_cf)
    flag_text = "\n".join(f"- ⚠ {f}" for f in flags) if flags else "- 未发现显著异常警示"
    text = (
        "### 现金流趋势（年报）\n"
        + md_table(
            ["报告期", "经营现金流", "资本开支", "自由现金流", "OCF/净利润", "投资现金流", "筹资现金流"],
            trend_rows,
        )
        + f"\n\n### 现金流类型\n最新年报归类：**{cf_type}**"
        + f"\n\n### 规则引擎警示\n{flag_text}"
    )

    return {"text": text, "flags": flags, "metrics": metrics, "cashflow_type": cf_type}
