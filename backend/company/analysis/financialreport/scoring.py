"""张新民八看综合诊断：连续 sigmoid 打分。

二~六看：水平分 + 变化分（各 50%）；七看逐项扣分；八看仅同比连续分；一看不计分。
"""

from __future__ import annotations

import math
from typing import Any

from company.analysis.financialreport._common import fmt_pct, fmt_x, fmt_yi, yoy
from company.analysis.financialreport.metrics import (
    cash_quality,
    classify_liabilities,
    competitiveness,
    core_profit,
    cost_structure,
    operating_cash,
    revenue,
)

# 方面权重：一看 0，二~八 15/15/20/10/15/15/10
ASPECT_WEIGHTS = [0, 15, 15, 20, 10, 15, 15, 10]
LEVEL_WEIGHT = 0.5
CHANGE_WEIGHT = 0.5
RISK_PER_HIT = 12.5

# 参数表：(x0, k) 水平；k_delta 变化；higher_is_better
PARAMS: dict[str, dict[str, Any]] = {
    "two_ends": {"x0": 1.0, "k": 2.0, "k_delta": 4.0, "higher": True},
    "gross_margin": {"x0": 25.0, "k": 0.12, "k_delta": 0.4, "higher": True},
    "core_margin": {"x0": 10.0, "k": 0.25, "k_delta": 0.5, "higher": True},
    "core_profit_yi": {"k_delta": 0.5, "higher": True},  # 仅变化，亿元差额
    "roe": {"x0": 10.0, "k": 0.25, "k_delta": 0.5, "higher": True},
    "cogs_rate": {"x0": 70.0, "k": 0.12, "k_delta": 0.12, "higher": False},
    "sale_exp": {"x0": 8.0, "k": 0.35, "k_delta": 0.35, "higher": False},
    "manage_exp": {"x0": 6.0, "k": 0.4, "k_delta": 0.4, "higher": False},
    "rd_exp": {"x0": 5.0, "k": 0.35, "k_delta": 0.35, "higher": False},
    "fin_exp": {"x0": 2.0, "k": 0.8, "k_delta": 0.8, "higher": False},
    "fin_liab": {"x0": 40.0, "k": 0.08, "k_delta": 0.08, "higher": False},
    "op_liab": {"x0": 50.0, "k": 0.08, "k_delta": 0.08, "higher": True},
    "fcf_rev": {"x0": 5.0, "k": 0.2, "k_delta": 0.2, "higher": True},
    "ocf_core": {"x0": 90.0, "k": 0.06, "k_delta": 0.06, "higher": True},
    "outlook_yoy": {"x0": 0.0, "k": 0.04, "higher": True},
}

OCF_CORE_QUAD_OCF_POS = 60.0
OCF_CORE_QUAD_BOTH_NEG = 25.0

OUTLOOK_TURNAROUND = 75.0  # 扭亏
OUTLOOK_NARROW = 65.0  # 减亏
OUTLOOK_WIDEN = 25.0  # 扩亏
OUTLOOK_SLIP = 20.0  # 转亏


def sigmoid_score(x: float, x0: float, k: float, *, higher_is_better: bool = True) -> float:
    """连续分 0~100；越高越好用 sigmoid，越低越好用 100−sigmoid。"""
    raw = 100.0 / (1.0 + math.exp(-k * (x - x0)))
    score = raw if higher_is_better else 100.0 - raw
    return float(score)


def level_score(
    x: float | None,
    x0: float,
    k: float,
    *,
    higher_is_better: bool = True,
) -> float | None:
    if x is None:
        return None
    return sigmoid_score(x, x0, k, higher_is_better=higher_is_better)


def change_score(
    delta: float | None,
    k_delta: float,
    *,
    higher_is_better: bool = True,
) -> float | None:
    """变化分：锚点固定 0（持平约 50）。"""
    if delta is None:
        return None
    return sigmoid_score(delta, 0.0, k_delta, higher_is_better=higher_is_better)


def blend(level: float | None, change: float | None) -> float | None:
    """水平/变化各 50%；缺变化只用水平；缺水平则整项缺失。"""
    if level is None:
        return None
    if change is None:
        return level
    return LEVEL_WEIGHT * level + CHANGE_WEIGHT * change


def mean_scores(scores: list[float | None]) -> float | None:
    vals = [s for s in scores if s is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def weighted_total(
    aspect_scores: list[float | None],
    weights: list[float] | None = None,
) -> float | None:
    """方面缺失则剔除并对其余权重重归一。``aspect_scores`` 对应二~八看（7 项）或含一看的 8 项。"""
    w = list(weights if weights is not None else ASPECT_WEIGHTS)
    if len(aspect_scores) == 7 and len(w) == 8:
        # 传入的是二~八看分数，权重跳过一看
        pairs = list(zip(aspect_scores, w[1:]))
    else:
        pairs = list(zip(aspect_scores, w[: len(aspect_scores)]))
    usable = [(s, wt) for s, wt in pairs if s is not None and wt > 0]
    if not usable:
        return None
    total_w = sum(wt for _, wt in usable)
    if total_w <= 0:
        return None
    return round(sum(s * wt for s, wt in usable) / total_w)


def _metric(
    name: str,
    *,
    value: float | None = None,
    delta: float | None = None,
    level: float | None = None,
    change: float | None = None,
    score: float | None = None,
    note: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "delta": delta,
        "level_score": None if level is None else round(level, 2),
        "change_score": None if change is None else round(change, 2),
        "score": None if score is None else round(score, 2),
        "note": note,
    }


def _delta(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev is None:
        return None
    return curr - prev


def score_ocf_core_level(ocf: float | None, core: float | None) -> tuple[float | None, float | None, str]:
    """返回 (水平分, 可用比率值, note)。核心利润>0 用比率；否则象限分。"""
    if ocf is None or core is None:
        return None, None, "缺数据"
    if core > 0:
        ratio = ocf / core * 100.0
        p = PARAMS["ocf_core"]
        return level_score(ratio, p["x0"], p["k"], higher_is_better=True), ratio, ""
    if ocf > 0:
        return OCF_CORE_QUAD_OCF_POS, None, "核心利润≤0且OCF>0：象限分60"
    return OCF_CORE_QUAD_BOTH_NEG, None, "核心利润≤0且OCF≤0：象限分25"


def score_outlook_leg(curr: float | None, prev: float | None) -> tuple[float | None, float | None, str]:
    """单路前景分。(score, yoy_or_none, note)"""
    if curr is None or prev is None:
        return None, None, "缺数据"
    if prev > 0:
        rate = yoy(curr, prev)
        if rate is None:
            return None, None, "缺数据"
        p = PARAMS["outlook_yoy"]
        return level_score(rate, p["x0"], p["k"], higher_is_better=True), rate, ""
    # 上期 ≤ 0：扭亏/减亏/扩亏/转亏
    if prev < 0 and curr > 0:
        return OUTLOOK_TURNAROUND, None, "扭亏"
    if prev < 0 and curr < 0:
        if curr > prev:  # 亏得更少（如 -0.1 > -1）
            return OUTLOOK_NARROW, None, "减亏"
        if curr < prev:
            return OUTLOOK_WIDEN, None, "扩亏"
        return None, None, "持平无法判定"
    if prev < 0 and curr == 0:
        return OUTLOOK_NARROW, None, "减亏至零"
    if prev == 0 and curr > 0:
        return OUTLOOK_TURNAROUND, None, "由零转正"
    if prev == 0 and curr < 0:
        return OUTLOOK_SLIP, None, "由零转亏"
    if prev >= 0 and curr < 0:
        return OUTLOOK_SLIP, None, "转亏"
    if prev == 0 and curr == 0:
        return None, None, "无法判定"
    return None, None, "无法判定"


def _fmt_score(s: float | None) -> str:
    if s is None:
        return "—"
    return f"{round(s)}"


def compute_scores(
    series: list[dict[str, Any]],
    bundle: dict[str, Any],
    *,
    risk_count: int = 0,
) -> dict[str, Any]:
    """计算综合诊断连续分，返回 aspects / score_total / score_weights 等。"""
    latest = series[0] if series else {}
    prev = series[1] if len(series) > 1 else None

    profit = bundle.get("profit") or (core_profit(latest) if latest else {})
    cash = bundle.get("cash") or (cash_quality(latest, prev) if latest else {})
    comp = bundle.get("competitiveness") or (competitiveness(latest) if latest else {})
    liab = classify_liabilities(latest) if latest else {}
    prev_liab = classify_liabilities(prev) if prev else {}
    prev_profit = core_profit(prev) if prev else {}
    prev_cash = cash_quality(prev, series[2] if prev and len(series) > 2 else None) if prev else {}
    prev_comp = competitiveness(prev) if prev else {}
    cost = cost_structure(latest).get("rates", {}) if latest else {}
    prev_cost = cost_structure(prev).get("rates", {}) if prev else {}

    rev = revenue(latest) if latest else None
    prev_rev = revenue(prev) if prev else None
    rates_ok = rev is not None and rev > 0
    prev_rates_ok = prev_rev is not None and prev_rev > 0

    aspects: list[dict[str, Any]] = []

    # —— 一看：不计分 ——
    strategy = bundle.get("strategy") or {}
    aspects.append(
        {
            "key": "strategy",
            "name": "战略方向（一看）",
            "score": None,
            "weight": ASPECT_WEIGHTS[0],
            "metrics": [],
            "evaluation": strategy.get("strategy_type", "—"),
            "evidence": (
                f"经营{fmt_pct(strategy.get('operating_asset_ratio'))} / "
                f"投资{fmt_pct(strategy.get('investing_asset_ratio'))}"
            ),
        }
    )

    # —— 二看 ——
    p_te, p_gm = PARAMS["two_ends"], PARAMS["gross_margin"]
    te = comp.get("two_ends_index")
    te_prev = prev_comp.get("two_ends_index")
    te_d = _delta(te, te_prev)
    te_l = level_score(te, p_te["x0"], p_te["k"], higher_is_better=True)
    te_c = change_score(te_d, p_te["k_delta"], higher_is_better=True)
    te_s = blend(te_l, te_c)

    gm = profit.get("gross_margin")
    gm_prev = prev_profit.get("gross_margin")
    gm_d = _delta(gm, gm_prev)
    gm_l = level_score(gm, p_gm["x0"], p_gm["k"], higher_is_better=True)
    gm_c = change_score(gm_d, p_gm["k_delta"], higher_is_better=True)
    gm_s = blend(gm_l, gm_c)

    s2 = mean_scores([te_s, gm_s])
    aspects.append(
        {
            "key": "operating",
            "name": "竞争力（二看）",
            "score": None if s2 is None else round(s2, 2),
            "weight": ASPECT_WEIGHTS[1],
            "metrics": [
                _metric(
                    "两头吃指数",
                    value=te,
                    delta=te_d,
                    level=te_l,
                    change=te_c,
                    score=te_s,
                ),
                _metric(
                    "毛利率",
                    value=gm,
                    delta=gm_d,
                    level=gm_l,
                    change=gm_c,
                    score=gm_s,
                ),
            ],
            "evaluation": _fmt_score(s2),
            "evidence": (
                f"两头吃 {fmt_x(te)}（Δ {fmt_x(te_d)}，分 {_fmt_score(te_s)}）；"
                f"毛利率 {fmt_pct(gm)}（Δ {fmt_pct(gm_d)}，分 {_fmt_score(gm_s)}）"
            ),
        }
    )

    # —— 三看 ——
    p_cm = PARAMS["core_margin"]
    cm = profit.get("core_margin") if rates_ok else None
    cm_prev = prev_profit.get("core_margin") if prev_rates_ok else None
    # 若营收异常，core_margin 可能仍有值；严格按计划：营收≤0 则利润率缺失
    if not rates_ok:
        cm = None
    if not prev_rates_ok:
        cm_prev = None
    cm_d = _delta(cm, cm_prev)
    cm_l = level_score(cm, p_cm["x0"], p_cm["k"], higher_is_better=True)
    cm_c = change_score(cm_d, p_cm["k_delta"], higher_is_better=True)
    cm_s = blend(cm_l, cm_c)

    core = profit.get("core_profit")
    core_prev = prev_profit.get("core_profit")
    core_d_yi = None
    if core is not None and core_prev is not None:
        core_d_yi = (core - core_prev) / 1e8
    core_c = change_score(core_d_yi, PARAMS["core_profit_yi"]["k_delta"], higher_is_better=True)
    # 金额槽只有变化分
    core_s = core_c

    s3 = mean_scores([cm_s, core_s])
    aspects.append(
        {
            "key": "profit",
            "name": "效益质量（三看）",
            "score": None if s3 is None else round(s3, 2),
            "weight": ASPECT_WEIGHTS[2],
            "metrics": [
                _metric(
                    "核心利润率",
                    value=cm,
                    delta=cm_d,
                    level=cm_l,
                    change=cm_c,
                    score=cm_s,
                ),
                _metric(
                    "核心利润",
                    value=core,
                    delta=core_d_yi,
                    level=None,
                    change=core_c,
                    score=core_s,
                    note="仅变化分（亿元差额）",
                ),
            ],
            "evaluation": _fmt_score(s3),
            "evidence": (
                f"核心利润率 {fmt_pct(cm)}（分 {_fmt_score(cm_s)}）；"
                f"核心利润 {fmt_yi(core)}（Δ {fmt_yi(None if core_d_yi is None else core_d_yi * 1e8)}，"
                f"变化分 {_fmt_score(core_c)}）"
            ),
        }
    )

    # —— 四看 ——
    p_roe = PARAMS["roe"]
    roe = profit.get("roe")
    roe_prev = prev_profit.get("roe")
    roe_d = _delta(roe, roe_prev)
    roe_l = level_score(roe, p_roe["x0"], p_roe["k"], higher_is_better=True)
    roe_c = change_score(roe_d, p_roe["k_delta"], higher_is_better=True)
    roe_s = blend(roe_l, roe_c)
    aspects.append(
        {
            "key": "value",
            "name": "价值创造（四看）",
            "score": None if roe_s is None else round(roe_s, 2),
            "weight": ASPECT_WEIGHTS[3],
            "metrics": [
                _metric(
                    "ROE",
                    value=roe,
                    delta=roe_d,
                    level=roe_l,
                    change=roe_c,
                    score=roe_s,
                ),
            ],
            "evaluation": _fmt_score(roe_s),
            "evidence": f"ROE {fmt_pct(roe)}（上期 {fmt_pct(roe_prev)}，Δ {fmt_pct(roe_d)}）",
        }
    )

    # —— 五看 ——
    def _rate_metric(key: str, label: str, param_key: str) -> dict[str, Any]:
        p = PARAMS[param_key]
        cur = cost.get(key) if rates_ok else None
        prv = prev_cost.get(key) if prev_rates_ok else None
        d = _delta(cur, prv)
        lv = level_score(cur, p["x0"], p["k"], higher_is_better=p["higher"])
        ch = change_score(d, p["k_delta"], higher_is_better=p["higher"])
        sc = blend(lv, ch)
        return _metric(label, value=cur, delta=d, level=lv, change=ch, score=sc)

    m_cogs = _rate_metric("营业成本率", "营业成本率", "cogs_rate")
    m_sale = _rate_metric("销售费用率", "销售费用率", "sale_exp")
    m_mgmt = _rate_metric("管理费用率", "管理费用率", "manage_exp")
    m_rd = _rate_metric("研发费用率", "研发费用率", "rd_exp")
    m_fin = _rate_metric("财务费用率", "财务费用率", "fin_exp")
    period_block = mean_scores(
        [m_sale["score"], m_mgmt["score"], m_rd["score"], m_fin["score"]]
    )
    s5 = mean_scores([m_cogs["score"], period_block])
    aspects.append(
        {
            "key": "cost",
            "name": "成本控制（五看）",
            "score": None if s5 is None else round(s5, 2),
            "weight": ASPECT_WEIGHTS[4],
            "metrics": [m_cogs, m_sale, m_mgmt, m_rd, m_fin],
            "evaluation": _fmt_score(s5),
            "evidence": (
                f"营业成本率分 {_fmt_score(m_cogs['score'])}；"
                f"期间费用块分 {_fmt_score(period_block)}"
            ),
        }
    )

    # —— 六看 ——
    p_fl, p_ol = PARAMS["fin_liab"], PARAMS["op_liab"]
    fl = liab.get("financial_ratio")
    fl_prev = prev_liab.get("financial_ratio")
    fl_d = _delta(fl, fl_prev)
    fl_l = level_score(fl, p_fl["x0"], p_fl["k"], higher_is_better=False)
    fl_c = change_score(fl_d, p_fl["k_delta"], higher_is_better=False)
    fl_s = blend(fl_l, fl_c)

    ol = liab.get("operating_ratio")
    ol_prev = prev_liab.get("operating_ratio")
    ol_d = _delta(ol, ol_prev)
    ol_l = level_score(ol, p_ol["x0"], p_ol["k"], higher_is_better=True)
    ol_c = change_score(ol_d, p_ol["k_delta"], higher_is_better=True)
    ol_s = blend(ol_l, ol_c)

    fcf = cash.get("fcf")
    fcf_prev = prev_cash.get("fcf")
    fcf_rev = (fcf / rev * 100.0) if fcf is not None and rates_ok else None
    fcf_rev_prev = (
        (fcf_prev / prev_rev * 100.0) if fcf_prev is not None and prev_rates_ok else None
    )
    p_fr = PARAMS["fcf_rev"]
    fr_d = _delta(fcf_rev, fcf_rev_prev)
    fr_l = level_score(fcf_rev, p_fr["x0"], p_fr["k"], higher_is_better=True)
    fr_c = change_score(fr_d, p_fr["k_delta"], higher_is_better=True)
    fr_s = blend(fr_l, fr_c)

    ocf = cash.get("ocf")
    core_val = profit.get("core_profit")
    ocf_l, ocf_ratio, ocf_note = score_ocf_core_level(ocf, core_val)
    ocf_c = None
    ocf_d = None
    prev_core = prev_profit.get("core_profit")
    prev_ocf = prev_cash.get("ocf")
    if (
        ocf_ratio is not None
        and prev_ocf is not None
        and prev_core is not None
        and prev_core > 0
        and core_val is not None
        and core_val > 0
    ):
        prev_ratio = prev_ocf / prev_core * 100.0
        ocf_d = ocf_ratio - prev_ratio
        ocf_c = change_score(ocf_d, PARAMS["ocf_core"]["k_delta"], higher_is_better=True)
    # 象限分：无比率则无变化，指标分=水平分
    if ocf_ratio is None:
        ocf_s = ocf_l
    else:
        ocf_s = blend(ocf_l, ocf_c)

    s6 = mean_scores([fl_s, ol_s, fr_s, ocf_s])
    aspects.append(
        {
            "key": "quality",
            "name": "财务状况质量（六看）",
            "score": None if s6 is None else round(s6, 2),
            "weight": ASPECT_WEIGHTS[5],
            "metrics": [
                _metric(
                    "金融性负债占比",
                    value=fl,
                    delta=fl_d,
                    level=fl_l,
                    change=fl_c,
                    score=fl_s,
                ),
                _metric(
                    "经营性负债占比",
                    value=ol,
                    delta=ol_d,
                    level=ol_l,
                    change=ol_c,
                    score=ol_s,
                ),
                _metric(
                    "FCF/营收",
                    value=fcf_rev,
                    delta=fr_d,
                    level=fr_l,
                    change=fr_c,
                    score=fr_s,
                ),
                _metric(
                    "OCF/核心利润",
                    value=ocf_ratio,
                    delta=ocf_d,
                    level=ocf_l,
                    change=ocf_c,
                    score=ocf_s,
                    note=ocf_note,
                ),
            ],
            "evaluation": _fmt_score(s6),
            "evidence": (
                f"金融负债占比 {fmt_pct(fl)}；经营负债占比 {fmt_pct(ol)}；"
                f"FCF/营收 {fmt_pct(fcf_rev)}；OCF/核心利润 {fmt_pct(ocf_ratio)}"
                + (f"（{ocf_note}）" if ocf_note else "")
            ),
        }
    )

    # —— 七看 ——
    s7 = max(0.0, 100.0 - RISK_PER_HIT * max(0, int(risk_count)))
    aspects.append(
        {
            "key": "risk",
            "name": "风险状况（七看）",
            "score": round(s7, 2),
            "weight": ASPECT_WEIGHTS[6],
            "metrics": [
                _metric(
                    "风险触发",
                    value=float(risk_count),
                    score=s7,
                    note=f"每项扣{RISK_PER_HIT}分",
                ),
            ],
            "evaluation": _fmt_score(s7),
            "evidence": "",  # 由 build_summary 填触发明细
        }
    )

    # —— 八看 ——
    rev_s, rev_y, rev_n = score_outlook_leg(rev, prev_rev)
    core_s8, core_y, core_n = score_outlook_leg(core_val, prev_profit.get("core_profit"))
    ocf_now = operating_cash(latest) if latest else None
    ocf_was = operating_cash(prev) if prev else None
    ocf_s8, ocf_y, ocf_n = score_outlook_leg(ocf_now, ocf_was)
    s8 = mean_scores([rev_s, core_s8, ocf_s8])
    aspects.append(
        {
            "key": "outlook",
            "name": "前景（八看）",
            "score": None if s8 is None else round(s8, 2),
            "weight": ASPECT_WEIGHTS[7],
            "metrics": [
                _metric("营收同比", value=rev_y, score=rev_s, note=rev_n),
                _metric("核心利润同比", value=core_y, score=core_s8, note=core_n),
                _metric("经营现金流同比", value=ocf_y, score=ocf_s8, note=ocf_n),
            ],
            "evaluation": _fmt_score(s8),
            "evidence": (
                f"营收同比 {fmt_pct(rev_y)}（{_fmt_score(rev_s)}"
                + (f"，{rev_n}" if rev_n else "")
                + "）；"
                f"核心利润同比 {fmt_pct(core_y)}（{_fmt_score(core_s8)}"
                + (f"，{core_n}" if core_n else "")
                + "）；"
                f"经营现金流同比 {fmt_pct(ocf_y)}（{_fmt_score(ocf_s8)}"
                + (f"，{ocf_n}" if ocf_n else "")
                + "）"
            ),
        }
    )

    # 总分：二~八看
    scored = [a["score"] for a in aspects[1:]]
    total = weighted_total(scored, ASPECT_WEIGHTS)

    return {
        "aspects": aspects,
        "score_total": total,
        "score_weights": list(ASPECT_WEIGHTS),
        "score_weights_effective": _effective_weights(scored),
    }


def _effective_weights(aspect_scores_2_to_8: list[float | None]) -> list[float]:
    """返回含一看的 8 项有效权重（缺失方面权重归零后按比例放大剩余）。"""
    base = ASPECT_WEIGHTS[1:]
    usable_w = sum(w for s, w in zip(aspect_scores_2_to_8, base) if s is not None)
    if usable_w <= 0:
        return list(ASPECT_WEIGHTS)
    out = [0.0]
    for s, w in zip(aspect_scores_2_to_8, base):
        if s is None:
            out.append(0.0)
        else:
            out.append(round(w * 100.0 / usable_w, 2))
    return out
