"""资产负债表规则引擎。"""

from __future__ import annotations

from typing import Any

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


def analyze_balance_sheet(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """分析资产负债表，返回指标表、警示与 Markdown 摘要。"""
    if not rows:
        return {"text": "（未能获取资产负债表数据）", "flags": [], "metrics": {}}

    annual = rows[:5]
    latest = annual[0]
    prev = annual[1] if len(annual) > 1 else {}

    flags: list[str] = []
    metrics: dict[str, Any] = {}

    cash = to_float(pick(latest, "MONETARYFUNDS"))
    assets = to_float(pick(latest, "TOTAL_ASSETS_PK", "TOTAL_ASSETS"))
    liab = to_float(pick(latest, "LIABILITY", "TOTAL_LIABILITIES"))
    equity = to_float(pick(latest, "TOTAL_EQUITY_PK", "TOTAL_EQUITY"))
    recv = to_float(pick(latest, "ACCOUNTS_RECE"))
    inventory = to_float(pick(latest, "INVENTORY"))
    short_loan = to_float(pick(latest, "SHORT_LOAN"))
    debt_ratio = to_float(pick(latest, "ZCFZL", "DEBT_ASSET_RATIO"))
    current_ratio = to_float(pick(latest, "LD", "CURRENT_RATIO"))
    quick_ratio = to_float(pick(latest, "SD"))

    if current_ratio and current_ratio > 50:
        current_ratio /= 100
    if quick_ratio and quick_ratio > 50:
        quick_ratio /= 100

    metrics.update(
        {
            "cash": cash,
            "assets": assets,
            "liab": liab,
            "equity": equity,
            "debt_ratio": debt_ratio,
            "current_ratio": current_ratio,
            "quick_ratio": quick_ratio,
        }
    )

    if debt_ratio is not None and debt_ratio > 70:
        flags.append(f"资产负债率偏高：{fmt_pct(debt_ratio)}")
    if current_ratio is not None and current_ratio < 1:
        flags.append(f"流动比率低于 1：{fmt_x(current_ratio)}，短期偿债压力需关注")
    if short_loan and liab and short_loan / liab > 0.6:
        flags.append("短期借款占负债比例较高，需关注再融资与流动性")

    recv_yoy = yoy(recv, pick(prev, "ACCOUNTS_RECE"))
    inv_yoy = yoy(inventory, pick(prev, "INVENTORY"))
    assets_yoy = yoy(assets, pick(prev, "TOTAL_ASSETS_PK", "TOTAL_ASSETS"))
    if recv_yoy is not None and recv_yoy > 30:
        flags.append(f"应收账款同比大增 {fmt_pct(recv_yoy)}，需核对收入质量")
    if inv_yoy is not None and inv_yoy > 30:
        flags.append(f"存货同比大增 {fmt_pct(inv_yoy)}，需关注去化与跌价风险")

    trend_rows: list[list[str]] = []
    for row in annual:
        cr = to_float(pick(row, "LD", "CURRENT_RATIO"))
        qr = to_float(pick(row, "SD"))
        if cr and cr > 50:
            cr /= 100
        if qr and qr > 50:
            qr /= 100
        ta = to_float(pick(row, "TOTAL_ASSETS_PK", "TOTAL_ASSETS"))
        recv_v = to_float(pick(row, "ACCOUNTS_RECE"))
        recv_ratio = (recv_v / ta * 100) if recv_v and ta else None
        trend_rows.append(
            [
                period_label(row),
                fmt_yi(pick(row, "MONETARYFUNDS")),
                fmt_yi(ta),
                fmt_yi(pick(row, "LIABILITY", "TOTAL_LIABILITIES")),
                fmt_yi(pick(row, "TOTAL_EQUITY_PK", "TOTAL_EQUITY")),
                fmt_pct(pick(row, "ZCFZL", "DEBT_ASSET_RATIO")),
                fmt_x(cr),
                fmt_x(qr),
                fmt_pct(recv_ratio) if recv_ratio is not None else "—",
            ]
        )

    structure_rows: list[list[str]] = []
    if assets:
        for label, val in (
            ("货币资金", cash),
            ("应收账款", recv),
            ("存货", inventory),
            ("总资产", assets),
        ):
            ratio = (val / assets * 100) if val else None
            structure_rows.append([label, fmt_yi(val), fmt_pct(ratio) if ratio else "—"])

    flag_text = "\n".join(f"- ⚠ {f}" for f in flags) if flags else "- 未发现显著异常警示"
    text = (
        "### 资产负债趋势\n"
        + md_table(
            ["报告期", "货币资金", "总资产", "总负债", "净资产", "资产负债率", "流动比率", "速动比率", "应收/总资产"],
            trend_rows,
        )
        + "\n\n### 最新期资产结构\n"
        + md_table(["科目", "金额", "占总资产"], structure_rows)
        + f"\n\n### 规则引擎警示\n{flag_text}"
    )
    if assets_yoy is not None:
        text += f"\n\n> 总资产同比：{fmt_pct(assets_yoy)}"

    return {"text": text, "flags": flags, "metrics": metrics, "table": trend_rows}
