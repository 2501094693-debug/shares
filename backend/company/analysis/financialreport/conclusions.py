"""张新民「八看」：各看结论（自然语言条目）生成。

每一条都引用预计算数字，口径说明固定，不依赖模型。
"""

from __future__ import annotations

from typing import Any

from company.analysis.financialreport._common import (
    fmt_num,
    fmt_pct,
    fmt_x,
    fmt_yi,
    period_label,
)
from company.analysis.financialreport.metrics import (
    cash_quality,
    classify_assets,
    classify_liabilities,
    competitiveness,
    core_profit,
    cost_structure,
    grade,
    revenue,
    strategy_type,
    value_parts,
)


def ytd_note(row: dict[str, Any] | None) -> str:
    """非年报口径提示：利润表/现金流量表为累计数，不可与年报横比。"""
    if not row:
        return ""
    kind = report_kind(row)
    if kind == "年报":
        return ""
    return f"{period_label(row)}为{kind}累计口径，利润表/现金流量表不可与年报直接横比。"


def report_kind(row: dict[str, Any]) -> str:
    from company.analysis.financialreport._common import report_kind as _rk

    return _rk(row)


def asset_conclusions(series: list[dict[str, Any]]) -> list[str]:
    latest = series[0]
    prev = series[1] if len(series) > 1 else None
    assets = classify_assets(latest)
    strategy = strategy_type(latest, prev)
    total = assets.get("total_assets") or 1
    control_invest = (assets.get("long_equity_invest") or 0) + (assets.get("goodwill") or 0)
    control_pct = control_invest / total * 100 if total and control_invest else None
    op_yoy, inv_yoy = strategy.get("operating_asset_yoy"), strategy.get("investing_asset_yoy")
    direction = "扩张" if (op_yoy or 0) > 0 or (inv_yoy or 0) > 0 else "收缩"
    bullets = [
        ytd_note(latest),
        (
            f"战略判定：{period_label(latest)}经营性资产 {fmt_yi(assets.get('operating_assets'))}"
            f"（占比 {fmt_pct(strategy.get('operating_asset_ratio'))}），"
            f"投资性资产 {fmt_yi(assets.get('investing_assets'))}"
            f"（占比 {fmt_pct(strategy.get('investing_asset_ratio'))}）。"
            f"判定规则：投资占比>35%且投资增速快于经营 → 投资主导；经营占比>65% → 经营主导；否则混合。"
            f"本期判定为 **{strategy.get('strategy_type')}**。"
        ),
        (
            f"边际方向：经营性资产同比 {fmt_pct(op_yoy)}，投资性资产同比 {fmt_pct(inv_yoy)}，"
            f"整体处于 **{direction}** 态势。"
            if prev
            else ""
        ),
        (
            f"结构特征：重资产率（固定资产÷总资产）{fmt_pct(strategy.get('heavy_asset_ratio'))}；"
            f"控制性投资（长期股权投资+商誉）{fmt_yi(control_invest)}，占资产 {fmt_pct(control_pct)}。"
        ),
    ]
    return [item for item in bullets if item]


def liability_conclusions(series: list[dict[str, Any]]) -> list[str]:
    latest = series[0]
    liab = classify_liabilities(latest)
    assets = classify_assets(latest)
    bullets = [
        ytd_note(latest),
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
        bullets.append(f"货币资金 {fmt_yi(cash_val)} 同时短期借款 {fmt_yi(short_loan)}，存在存贷双高迹象。")
    return [item for item in bullets if item]


def core_profit_conclusions(series: list[dict[str, Any]]) -> list[str]:
    latest = series[0]
    prev = series[1] if len(series) > 1 else None
    p = core_profit(latest)
    prev_p = core_profit(prev) if prev else None
    gm, cm = p.get("gross_margin"), p.get("core_margin")
    gap = (gm - cm) if gm is not None and cm is not None else None
    bullets = [
        ytd_note(latest),
        (
            f"代入公式：营业收入 {fmt_yi(p.get('revenue'))} − 营业成本 {fmt_yi(p.get('cogs'))}"
            f" − 税金及附加 {fmt_yi(p.get('taxes'))} − 销售/管理/研发/财务费用 {fmt_yi(p.get('expenses'))}"
            f" = 核心利润 {fmt_yi(p.get('core_profit'))}，核心利润率 {fmt_pct(p.get('core_margin'))}。"
        ),
        f"毛利率 {fmt_pct(gm)}"
        + (f"，与核心利润率相差 {fmt_num(gap, 2)} 个百分点，差距来自税金及期间费用。" if gap is not None else "。"),
    ]
    if prev_p:
        from company.analysis.financialreport._common import yoy

        bullets.append(
            f"相对上一期同口径{period_label(prev)}核心利润 {fmt_yi(prev_p.get('core_profit'))}，"
            f"本期核心利润同比 {fmt_pct(yoy(p.get('core_profit'), prev_p.get('core_profit')))}。"
        )
    deduct = p.get("deduct_ratio")
    if deduct is not None:
        quality = "经常性利润占比较高" if deduct >= 70 else "扣非占比偏低，利润含非经常损益干扰"
        bullets.append(f"扣非净利润占归母净利润 {fmt_pct(deduct)}，{quality}。")
    return [item for item in bullets if item]


def cash_conclusions(series: list[dict[str, Any]]) -> list[str]:
    latest = series[0]
    prev = series[1] if len(series) > 1 else None
    c = cash_quality(latest, prev)
    evaluation = grade(c.get("ocf_core_ratio"), 100, 80)
    bullets = [
        ytd_note(latest),
        (
            f"{period_label(latest)}经营现金流 {fmt_yi(c.get('ocf'))}，自由现金流 {fmt_yi(c.get('fcf'))}。"
            f"OCF/核心利润 {fmt_pct(c.get('ocf_core_ratio'))}（≥100%优、≥80%中），评价为 **{evaluation}**。"
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


def competitiveness_conclusions(series: list[dict[str, Any]]) -> list[str]:
    latest = series[0]
    c = competitiveness(latest)
    p = core_profit(latest)
    a = classify_assets(latest)
    total = a.get("total_assets") or 0
    two_gold = a.get("two_gold")
    two_gold_pct = two_gold / total * 100 if two_gold and total else None
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
        ytd_note(latest),
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
        (
            f"营运资本占用：两金（应收+存货）{fmt_yi(two_gold)}，占总资产 {fmt_pct(two_gold_pct)}"
            + ("，占用偏高（>40%），需关注回款与去库存。" if two_gold_pct and two_gold_pct > 40 else "。")
        ),
    ]
    return [item for item in bullets if item]


def cost_conclusions(series: list[dict[str, Any]]) -> list[str]:
    latest = next((row for row in series if revenue(row)), None)
    if not latest:
        return ["营业收入缺失，无法拆成本结构。"]
    cs = cost_structure(latest)
    ranked = cs.get("ranked") or []
    top = f"占比最高的是{ranked[0][0]} {fmt_pct(ranked[0][1])}" if ranked else "各项费用率数据不足"
    return [
        ytd_note(latest),
        f"{period_label(latest)}营业收入 {fmt_yi(revenue(latest))}，{top}。",
        f"毛利率 {fmt_pct(cs.get('rates', {}).get('毛利率'))}。营业成本率与毛利率互为对照：毛利率优先取披露数，缺省时用 1−营业成本率。",
    ]


def value_conclusions(series: list[dict[str, Any]]) -> list[str]:
    latest = series[0]
    p = core_profit(latest)
    d = value_parts(latest, p)
    roe = p.get("roe")
    evaluation = grade(roe, 15, 8)
    return [
        ytd_note(latest),
        f"{period_label(latest)}ROE {fmt_pct(roe)}（≥15%优、≥8%中），评价为 **{evaluation}**；"
        f"ROA {fmt_pct(d.get('roa'))}。",
        (
            f"杜邦拆解：净利率 {fmt_pct(p.get('net_margin'))} × 资产周转 {fmt_x(d.get('asset_turnover'))}"
            f" × 权益乘数 {fmt_x(d.get('equity_multiplier'))}。"
        ),
        f"归母净利润 {fmt_yi(p.get('net_profit'))}，净资产 {fmt_yi(d.get('equity'))}。",
    ]


def outlook_conclusions(series: list[dict[str, Any]]) -> list[str]:
    if not series:
        return ["未能获取定期报告。"]
    latest, prev = series[0], (series[1] if len(series) > 1 else None)
    assets = classify_assets(latest)
    prev_assets = classify_assets(prev) if prev else {}
    op_yoy = _yoy(assets.get("operating_assets"), prev_assets.get("operating_assets"))
    inv_yoy = _yoy(assets.get("investing_assets"), prev_assets.get("investing_assets"))
    p = core_profit(latest)
    prev_p = core_profit(prev) if prev else {}
    core_yoy = _yoy(p.get("core_profit"), prev_p.get("core_profit"))
    c = cash_quality(latest, prev)
    ocf_yoy = c.get("ocf_yoy")

    expand = "扩张" if (op_yoy or 0) > 0 or (inv_yoy or 0) > 0 else "收缩"
    sync_ok = (
        op_yoy is not None
        and core_yoy is not None
        and ocf_yoy is not None
        and op_yoy > 0
        and core_yoy > 0
        and ocf_yoy > 0
    )
    bullets = [
        ytd_note(latest),
        (
            f"从资产结构看整体处于 **{expand}** 态势：经营性资产同比 {fmt_pct(op_yoy)}，"
            f"投资性资产同比 {fmt_pct(inv_yoy)}。"
        ),
        (
            f"经营性资产、核心利润、经营现金流三者"
            + ("同向改善，增长较自洽。" if sync_ok else "未同步改善，增长质量待观察。")
            + f"（核心利润同比 {fmt_pct(core_yoy)}，经营现金流同比 {fmt_pct(ocf_yoy)}）"
        ),
        "需跟踪指标：核心利润率、OCF/核心利润、两头吃指数、两金占比、有息负债率。",
    ]
    return [item for item in bullets if item]


def diagnosis_conclusions(metrics: dict[str, Any], flags: list[str], rows: list[list[str]]) -> list[str]:
    bullets = [
        f"数据覆盖：{metrics.get('coverage') or '—'}。最新定期报告 {metrics.get('latest_period') or '—'}"
        f"（{metrics.get('period_kind') or '定期报告'}）。"
    ]
    for dim, evaluation, evidence in rows:
        if dim in {"最新定期报告", "数据覆盖"}:
            continue
        bullets.append(f"{dim}：{evaluation}（{evidence}）。")
    if flags:
        bullets.append("风险警示：" + "；".join(flags) + "。")
    else:
        bullets.append("规则引擎未触发重大风险警示。")
    return bullets


def _yoy(curr: Any, prev: Any) -> float | None:
    from company.analysis.financialreport._common import yoy

    return yoy(curr, prev)
