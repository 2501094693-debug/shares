"""估值分析逐步报告：每一步「数据 → 公式（含义/怎么看）→ 结果」，末尾总结。

结构对齐财报八看的 view 形态，便于前端按同一套 zv-body 渲染。
"""

from __future__ import annotations

from typing import Any

from company.analysis.financialreport._common import fmt_num, fmt_pct, fmt_yi, md_table
from core.fmt import to_float

from .dcf import DcfResult
from .relative import RelativeResult, _MULTIPLE_LABELS


def _formula(
    name: str,
    formula: str,
    *,
    meaning: str = "",
    reading: str = "",
) -> dict[str, str]:
    return {
        "name": name,
        "formula": formula,
        "meaning": meaning,
        "reading": reading,
    }


def _step(
    *,
    key: str,
    no: int,
    name: str,
    raw: str,
    formulas: list[dict[str, str]],
    results: str,
    conclusions: list[str] | None = None,
) -> dict[str, Any]:
    items = [c for c in (conclusions or []) if c]
    return {
        "key": key,
        "no": no,
        "name": name,
        "raw": (raw or "").strip(),
        "formulas": formulas,
        "results": (results or "").strip(),
        "conclusions": items,
        "text": _step_text(raw, formulas, results, items),
    }


def _step_text(
    raw: str,
    formulas: list[dict[str, str]],
    results: str,
    conclusions: list[str],
) -> str:
    """Markdown：数据 → 计算公式（含义/怎么看）→ 结果 → 结论。"""
    lines: list[str] = []
    raw_text = (raw or "").strip()
    results_text = (results or "").strip()
    if raw_text:
        lines += ["#### 数据", "", raw_text, ""]
    lines += ["#### 计算公式", ""]
    if formulas:
        for f in formulas:
            lines.append(f"- **{f['name']}**：{f['formula']}")
            if f.get("meaning"):
                lines.append(f"  - 含义：{f['meaning']}")
            if f.get("reading"):
                lines.append(f"  - 怎么看：{f['reading']}")
    else:
        lines.append("（本节无二次加工公式）")
    lines.append("")
    if results_text:
        lines += ["#### 结果", "", results_text, ""]
    if conclusions:
        lines += ["#### 结论", "", "\n".join(f"- {c}" for c in conclusions)]
    return "\n".join(lines).strip()


def _yi_line(label: str, value: Any) -> str:
    return f"- {label}：{fmt_yi(value)}"


def _pct_line(label: str, value: Any) -> str:
    return f"- {label}：{fmt_pct(value)}"


def _num_line(label: str, value: Any, unit: str = "") -> str:
    text = fmt_num(value)
    return f"- {label}：{text}{unit}" if text != "—" else f"- {label}：—"


# ---------------------------------------------------------------------------
# DCF 各步
# ---------------------------------------------------------------------------


_FCF_SOURCE_LABEL = {
    "fcff_back": "东财 FCFF_BACK",
    "fcff_forward": "东财 FCFF_FORWARD（FCFF_BACK 量级异常已弃用）",
    "ocf_minus_capex": "OCF − Capex 估算",
}


def _step_fcf_base(dcf: DcfResult | None, metrics: dict[str, Any] | None) -> dict[str, Any]:
    cash = (metrics or {}).get("cash") or {}
    profit = (metrics or {}).get("profit") or {}
    fcf = cash.get("fcf")
    ocf = cash.get("ocf")
    capex = cash.get("capex")
    net = profit.get("net_profit")
    source = cash.get("fcf_source")
    source_label = _FCF_SOURCE_LABEL.get(str(source or ""), str(source or "—"))

    raw_lines = [
        _yi_line("东财 FCFF_BACK", cash.get("fcff_back")),
        _yi_line("东财 FCFF_FORWARD", cash.get("fcff_forward")),
        _yi_line("OCF − Capex（估算）", cash.get("fcf_proxy")),
        _yi_line("经营活动现金流量净额 OCF", ocf),
        _yi_line("资本开支 Capex", capex),
        _yi_line("净利润（备用代理）", net),
        f"- 本步采用口径：{source_label}",
        _yi_line("采用的自由现金流 FCF", fcf),
    ]
    notes = list((dcf.notes if dcf else []) or [])
    # 只保留与基期 FCF 相关的说明
    fcf_notes = [n for n in notes if "FCF" in n or "经营现金流" in n or "净利润" in n or "FCFF" in n]
    if fcf_notes:
        raw_lines.append("")
        raw_lines.append("选用说明：")
        raw_lines.extend(f"- {n}" for n in fcf_notes)

    formulas = [
        _formula(
            "自由现金流 FCF",
            "优先取披露 FCFF（BACK→FORWARD）；若相对 OCF 量级异常（不足 OCF 的 1%）则弃用，改用 OCF − Capex；再不可用则以净利润作极保守代理",
            meaning="企业扣掉维持与扩张性资本开支后，真正可自由支配的现金，是 DCF 折现的起点。",
            reading="基期 FCF 越大越好；为负或长期偏弱时，后续内在价值可信度下降，需警惕增长假设是否站得住。若 FCFF_BACK 与 OCF 量级差过大，优先信 OCF/FORWARD。",
        ),
    ]
    base = dcf.fcf_base if dcf else None
    results = md_table(
        ["指标", "数值"],
        [["基期自由现金流 FCF₀", fmt_yi(base)]],
    )
    conc: list[str] = []
    if base is None:
        conc.append("无法确定基期自由现金流，后续 DCF 步骤无法计算。")
    elif base <= 0:
        conc.append(f"基期 FCF 为 {fmt_yi(base)}，对折现结果偏悲观，解读时需谨慎。")
    else:
        conc.append(f"基期自由现金流取 {fmt_yi(base)}，作为显性期与终值推算的起点。")

    return _step(
        key="fcf_base",
        no=1,
        name="第一步：基期自由现金流",
        raw="\n".join(raw_lines),
        formulas=formulas,
        results=results,
        conclusions=conc,
    )


def _step_growth(dcf: DcfResult | None, annual_series: list[dict[str, Any]] | None) -> dict[str, Any]:
    assum = (dcf.assumptions_used if dcf else {}) or {}
    growth = assum.get("first_stage_growth")
    cagr = dcf.revenue_cagr_used if dcf else None

    rev_rows: list[list[str]] = []
    for row in (annual_series or [])[:8]:
        date = str(row.get("REPORT_DATE") or row.get("PERIOD_LABEL") or "—")[:10]
        rev = to_float(
            row.get("TOTALOPERATEREVE")
            or row.get("TOTAL_OPERATE_INCOME")
            or row.get("OPERATE_INCOME_PK")
        )
        rev_rows.append([date, fmt_yi(rev)])

    raw_parts: list[str] = []
    if rev_rows:
        raw_parts.append(md_table(["报告期", "营业收入"], rev_rows))
    else:
        raw_parts.append("- 年度营收序列：不足或未提供")
    if cagr is not None:
        raw_parts.append(_pct_line("由营收推导的 CAGR（截断前参考）", cagr))

    formulas = [
        _formula(
            "营收复合增长率 CAGR",
            "CAGR = (最新营收 ÷ 最早营收)^(1/(期数−1)) − 1；再截断到 [-10%, 20%] 作为显性期增长率 g",
            meaning="用历史营收复合成长速度，保守估计未来显性预测期内自由现金流的年化增速。",
            reading="截断上限 20% 是为避免把短期爆发当永续；若历史为负增长，模型会压低显性期 FCF，内在价值更保守。",
        ),
    ]
    results = md_table(
        ["指标", "数值"],
        [
            ["显性期年复合增长率 g", fmt_pct(growth)],
            ["预测年数 n", str(assum.get("projection_years") or "—")],
        ],
    )
    conc: list[str] = []
    if growth is None:
        conc.append("未确定显性期增长率。")
    else:
        conc.append(f"显性期增长率取 {fmt_pct(growth)}，用于推算未来 {assum.get('projection_years') or '—'} 年的 FCF。")

    return _step(
        key="growth",
        no=2,
        name="第二步：显性期增长率",
        raw="\n".join(raw_parts),
        formulas=formulas,
        results=results,
        conclusions=conc,
    )


def _step_explicit(dcf: DcfResult | None) -> dict[str, Any]:
    assum = (dcf.assumptions_used if dcf else {}) or {}
    wacc = assum.get("wacc")
    growth = assum.get("first_stage_growth")
    years = assum.get("projection_years")
    fcf0 = dcf.fcf_base if dcf else None

    raw_lines = [
        _yi_line("基期自由现金流 FCF₀", fcf0),
        _pct_line("显性期增长率 g", growth),
        _pct_line("折现率 WACC", wacc),
        f"- 预测年数 n：{years if years is not None else '—'}",
    ]
    formulas = [
        _formula(
            "第 t 年自由现金流",
            "FCFₜ = FCF₀ × (1 + g)^t",
            meaning="假设基期现金流按固定复合增速增长，得到显性预测期内每年的预期自由现金流。",
            reading="g 越高，远期 FCF 越大；若 g 不可持续，内在价值会被高估。",
        ),
        _formula(
            "折现到今天的现值",
            "PVₜ = FCFₜ ÷ (1 + WACC)^t；显性期现值合计 PV_explicit = Σ PVₜ",
            meaning="把未来各年现金折成今天的钱；WACC 越高，同样一笔远期现金今天越不值钱。",
            reading="WACC 上调 1 个百分点往往明显压低 EV；对利率与风险溢价敏感的公司更要看敏感性表。",
        ),
    ]
    proj = list((dcf.fcf_projection if dcf else None) or [])
    rows = [
        [str(p.get("year")), fmt_yi(p.get("fcf")), fmt_yi(p.get("pv")), fmt_num(p.get("discount_factor"), 4)]
        for p in proj
    ]
    results = md_table(
        ["年份 t", "FCFₜ", "现值 PVₜ", "折现因子"],
        rows,
    ) if rows else "（无显性期明细）"
    if dcf and dcf.pv_explicit is not None:
        results += f"\n\n显性期现值合计 **PV_explicit = {fmt_yi(dcf.pv_explicit)}**"

    conc: list[str] = []
    if dcf and dcf.pv_explicit is not None:
        conc.append(f"显性期（{years} 年）现金流折现合计 {fmt_yi(dcf.pv_explicit)}。")
    else:
        conc.append("显性期折现未能算出。")

    return _step(
        key="explicit",
        no=3,
        name="第三步：显性期现金流折现",
        raw="\n".join(raw_lines),
        formulas=formulas,
        results=results,
        conclusions=conc,
    )


def _step_terminal(dcf: DcfResult | None) -> dict[str, Any]:
    assum = (dcf.assumptions_used if dcf else {}) or {}
    wacc = assum.get("wacc")
    tg = assum.get("terminal_growth")
    years = assum.get("projection_years")
    last_fcf = None
    if dcf and dcf.fcf_projection:
        last_fcf = dcf.fcf_projection[-1].get("fcf")

    raw_lines = [
        _yi_line(f"第 {years or 'n'} 年自由现金流 FCFₙ", last_fcf),
        _pct_line("永续增长率 g∞", tg),
        _pct_line("折现率 WACC", wacc),
        f"- 预测年数 n：{years if years is not None else '—'}",
    ]
    formulas = [
        _formula(
            "终值（戈登增长模型）",
            "TV = FCFₙ × (1 + g∞) ÷ (WACC − g∞)",
            meaning="假设显性期结束后，现金流以永续低速增长，把「从第 n+1 年起的全部未来现金」压缩成第 n 年末的一个终值。",
            reading="g∞ 必须小于 WACC；二者越接近，终值越大、对假设越敏感，需结合敏感性表看稳健性。",
        ),
        _formula(
            "终值折现",
            "PV_terminal = TV ÷ (1 + WACC)^n",
            meaning="把第 n 年末的终值再折回今天，与显性期现值相加才是企业价值。",
            reading="多数成熟公司里，终值占 EV 的大半；若 PV_terminal 占比过高，说明结论更依赖永续假设而非近五年经营。",
        ),
    ]
    results = md_table(
        ["指标", "数值"],
        [
            ["终值 TV（第 n 年末）", fmt_yi(dcf.terminal_value if dcf else None)],
            ["终值现值 PV_terminal", fmt_yi(dcf.pv_terminal if dcf else None)],
        ],
    )
    conc: list[str] = []
    if dcf and dcf.pv_terminal is not None:
        conc.append(f"终值现值 {fmt_yi(dcf.pv_terminal)}（永续增长 {fmt_pct(tg)}，WACC {fmt_pct(wacc)}）。")
    else:
        conc.append("终值未能算出。")

    return _step(
        key="terminal",
        no=4,
        name="第四步：终值与折现",
        raw="\n".join(raw_lines),
        formulas=formulas,
        results=results,
        conclusions=conc,
    )


def _step_equity(dcf: DcfResult | None, metrics: dict[str, Any] | None, profile: dict[str, Any] | None) -> dict[str, Any]:
    liab = (metrics or {}).get("liabilities") or {}
    assets = (metrics or {}).get("assets") or {}
    profile = profile or {}

    raw_lines = [
        _yi_line("显性期现值 PV_explicit", dcf.pv_explicit if dcf else None),
        _yi_line("终值现值 PV_terminal", dcf.pv_terminal if dcf else None),
        _yi_line("金融性负债 / 有息债", liab.get("financial_liabilities")),
        _yi_line("总负债（备用）", liab.get("total_liabilities")),
        _yi_line("货币资金", assets.get("cash")),
        _yi_line("净债务（模型采用）", dcf.net_debt if dcf else None),
        f"- 总股本：{profile.get('total_shares') or profile.get('share_capital') or '—'}",
        f"- 当前价：{fmt_num(dcf.current_price if dcf else profile.get('price'))} 元",
    ]
    formulas = [
        _formula(
            "企业价值 EV",
            "EV = PV_explicit + PV_terminal",
            meaning="把显性期与永续期全部自由现金流折到今天的总和，对应「整个企业」的运营价值。",
            reading="EV 是对经营资产的定价，还未扣掉债权人份额；要落到股东到手，还需减净债务。",
        ),
        _formula(
            "净债务",
            "净债务 = 有息债务 − 货币资金（缺有息债时用总负债代理）",
            meaning="债权人应得的大致份额；现金可抵消部分债务。",
            reading="净债务为正会拉低股权价值；货币资金充裕、净债务为负时，股权价值可高于 EV。",
        ),
        _formula(
            "股权价值与每股内在价值",
            "股权价值 = EV − 净债务；每股内在价值 = 股权价值 ÷ 总股本",
            meaning="股东理论上可分得的全部价值，再摊到每一股，便于和市价对比。",
            reading="每股内在价值显著高于市价，才谈得上安全边际；二者接近或倒挂则缺乏绝对估值上的便宜空间。",
        ),
    ]
    results = md_table(
        ["指标", "数值"],
        [
            ["企业价值 EV", fmt_yi(dcf.enterprise_value if dcf else None)],
            ["净债务", fmt_yi(dcf.net_debt if dcf else None)],
            ["股权价值", fmt_yi(dcf.equity_value if dcf else None)],
            ["每股内在价值", f"{fmt_num(dcf.intrinsic_value_per_share if dcf else None)} 元"],
            ["当前价", f"{fmt_num(dcf.current_price if dcf else None)} 元"],
        ],
    )
    conc: list[str] = []
    intrinsic = dcf.intrinsic_value_per_share if dcf else None
    if intrinsic is None:
        conc.append("未能算出每股内在价值（常因缺总股本或基期 FCF）。")
    else:
        conc.append(f"每股内在价值约 {fmt_num(intrinsic)} 元。")

    return _step(
        key="equity",
        no=5,
        name="第五步：企业价值与每股内在价值",
        raw="\n".join(raw_lines),
        formulas=formulas,
        results=results,
        conclusions=conc,
    )


# ---------------------------------------------------------------------------
# 相对估值各步
# ---------------------------------------------------------------------------


def _step_history(relative: RelativeResult | None) -> dict[str, Any]:
    rel = relative
    history = (rel.history if rel else {}) or {}
    span = (rel.history_span if rel else {}) or {}
    current = (rel.current if rel else {}) or {}

    raw_lines = [
        f"- 历史样本区间：{span.get('start') or '—'} ~ {span.get('end') or '—'}（{span.get('points') or 0} 个交易日）",
    ]
    for key in ("pe_ttm", "pb", "ps_ttm"):
        label = _MULTIPLE_LABELS.get(key, key)
        raw_lines.append(_num_line(f"当前{label}", current.get(key), " 倍"))

    formulas = [
        _formula(
            "历史分位",
            "分位 = (历史样本中小于当前值的个数 + 0.5×等于当前值的个数) ÷ 样本数 × 100%",
            meaning="衡量当前倍数在自身历史中的相对位置：0% 接近历史最低，100% 接近历史最高。",
            reading="≤20% 偏历史低估区，≥80% 偏历史高估区；中位附近多为合理区。低分位只说明「相对自己便宜」，不保证绝对便宜。",
        ),
        _formula(
            "历史综合判定",
            "对市盈率TTM、市净率、市销率TTM 三个核心倍数的分位取平均，再映射为低估/偏低/合理/偏高/高估区",
            meaning="用多倍数平均，降低单一倍数失真（如亏损期 PE 失效）带来的误判。",
            reading="综合落在低估区且同业也不贵时，相对估值更有说服力；仅一项偏低需结合基本面核对。",
        ),
    ]
    rows = []
    for key in ("pe_ttm", "pb", "ps_ttm"):
        h = history.get(key) or {}
        rows.append(
            [
                _MULTIPLE_LABELS.get(key, key),
                fmt_num(h.get("current")),
                fmt_num(h.get("median")),
                fmt_pct(h.get("percentile"), 0) if h.get("percentile") is not None else "—",
                str(h.get("samples") or 0),
            ]
        )
    summary = history.get("_summary") or {}
    results = md_table(
        ["倍数", "当前", "历史中位数", "历史分位", "样本数"],
        rows,
    )
    if summary.get("avg_percentile") is not None:
        results += f"\n\n核心倍数平均分位 **{fmt_pct(summary.get('avg_percentile'), 1)}** → {rel.history_verdict if rel else '—'}"

    conc = [f"历史判定：{(rel.history_verdict if rel else None) or '数据不足'}"]
    return _step(
        key="history",
        no=6,
        name="第六步：相对估值 · 历史分位",
        raw="\n".join(raw_lines),
        formulas=formulas,
        results=results,
        conclusions=conc,
    )


def _step_peers(relative: RelativeResult | None) -> dict[str, Any]:
    rel = relative
    peers = (rel.peers if rel else {}) or {}
    multiples = peers.get("multiples") or {}
    samples = peers.get("samples") or []

    raw_lines = [f"- 同业样本数：{peers.get('count') or len(samples) or 0}"]
    if samples:
        peer_rows = [
            [
                str(p.get("code") or ""),
                str(p.get("name") or ""),
                fmt_num(p.get("pe_ttm")),
                fmt_num(p.get("pb")),
                fmt_num(p.get("ps_ttm")),
            ]
            for p in samples[:12]
        ]
        raw_lines.append("")
        raw_lines.append(md_table(["代码", "名称", "PE_TTM", "PB", "PS_TTM"], peer_rows))
    else:
        raw_lines.append("- 同业倍数：未采集到")

    formulas = [
        _formula(
            "相对同业溢价/折价",
            "溢价% = (本司倍数 − 同业中位数) ÷ 同业中位数 × 100%；负值为折价",
            meaning="看当前估值相对可比公司中位数是贵还是便宜。",
            reading="折价≤−10% 偏便宜，溢价≥10% 偏贵；显著偏离时要先问「是否真可比」（增速、杠杆、盈利质量是否同档）。",
        ),
        _formula(
            "同业综合判定",
            "对 PE_TTM / PB / PS_TTM 溢价取平均，映射为显著低于/低于/相当/高于/显著高于同业",
            meaning="多倍数平均，避免单一倍数因会计或周期扭曲。",
            reading="与历史分位一起看：历史低估且低于同业 → 相对低估更扎实；历史合理但显著高于同业 → 更像结构性溢价。",
        ),
    ]
    rows = []
    for key in ("pe_ttm", "pb", "ps_ttm"):
        m = multiples.get(key) or {}
        prem = m.get("premium_pct")
        rows.append(
            [
                _MULTIPLE_LABELS.get(key, key),
                fmt_num(m.get("target")),
                fmt_num(m.get("peer_median")),
                fmt_pct(prem, 0) if prem is not None else "—",
                str(m.get("peer_samples") or 0),
                m.get("verdict") or "—",
            ]
        )
    results = md_table(
        ["倍数", "本司", "同业中位数", "溢价/折价", "样本", "判定"],
        rows,
    ) if rows else "（无同业对比）"
    summary = peers.get("_summary") or {}
    if summary.get("avg_premium_pct") is not None:
        results += f"\n\n核心倍数平均溢价 **{fmt_pct(summary.get('avg_premium_pct'), 1)}** → {rel.peer_verdict if rel else '—'}"

    conc = [
        f"同业判定：{(rel.peer_verdict if rel else None) or '数据不足'}",
        f"相对估值总体：{(rel.overall if rel else None) or '数据不足'}",
    ]
    return _step(
        key="peers",
        no=7,
        name="第七步：相对估值 · 同业对比",
        raw="\n".join(raw_lines),
        formulas=formulas,
        results=results,
        conclusions=conc,
    )


def _step_margin(
    dcf: DcfResult | None,
    relative: RelativeResult | None,
    margin_of_safety_pct: float | None,
    verdict: str,
) -> dict[str, Any]:
    intrinsic = dcf.intrinsic_value_per_share if dcf else None
    price = dcf.current_price if dcf else None
    mos = margin_of_safety_pct
    if mos is None and dcf is not None:
        mos = dcf.margin_of_safety_pct

    raw_lines = [
        _num_line("每股内在价值", intrinsic, " 元"),
        _num_line("当前价", price, " 元"),
        f"- 相对估值总体：{(relative.overall if relative else None) or '—'}",
        f"- DCF 安全边际（模型内）：{fmt_pct(dcf.margin_of_safety_pct) if dcf and dcf.margin_of_safety_pct is not None else '—'}",
        f"- 上行/下行空间（相对市价）：{fmt_pct(dcf.upside_downside_pct) if dcf and dcf.upside_downside_pct is not None else '—'}",
    ]
    formulas = [
        _formula(
            "安全边际",
            "安全边际% = (每股内在价值 − 当前价) ÷ 每股内在价值 × 100%",
            meaning="市价相对内在价值「留了多少折扣」；正值表示市价低于内在价值，负值表示市价更高。",
            reading="经验上 ≥30% 才称得上较充足；15%~30% 偏薄；接近 0 或为负则缺乏绝对估值上的保护垫。安全边际不是买卖指令，只是价格缓冲。",
        ),
        _formula(
            "综合定性",
            "结合 DCF 安全边际厚薄与相对估值（历史/同业）高低，给出可考虑 / 观望 / 回避等提示",
            meaning="绝对估值看「够不够便宜」，相对估值看「贵不贵在自己历史和同行里」；两者同向更有参考价值。",
            reading="两者都偏便宜才更接近「可考虑」；信号冲突宜观望；相对或绝对明显偏贵宜回避。不构成投资建议。",
        ),
    ]
    results = md_table(
        ["指标", "数值"],
        [
            ["安全边际", fmt_pct(mos)],
            ["综合结论", verdict or "数据不足"],
        ],
    )
    conc = [verdict or "数据不足，无法定论"]
    return _step(
        key="margin",
        no=8,
        name="第八步：安全边际与综合定性",
        raw="\n".join(raw_lines),
        formulas=formulas,
        results=results,
        conclusions=conc,
    )


# ---------------------------------------------------------------------------
# 总结
# ---------------------------------------------------------------------------


def _build_summary(
    *,
    code: str,
    name: str,
    dcf: DcfResult | None,
    relative: RelativeResult | None,
    margin_of_safety_pct: float | None,
    verdict: str,
    notes: list[str],
    errors: list[str],
) -> dict[str, Any]:
    assum = (dcf.assumptions_used if dcf else {}) or {}
    intrinsic = dcf.intrinsic_value_per_share if dcf else None
    price = dcf.current_price if dcf else None
    mos = margin_of_safety_pct
    if mos is None and dcf is not None:
        mos = dcf.margin_of_safety_pct

    paragraphs: list[str] = []
    title = f"{name or code}（{code}）"
    paragraphs.append(
        f"{title}本次估值采用 DCF 绝对估值与 PE/PB/PS 相对估值交叉校验。"
        f"显性期 {assum.get('projection_years') or '—'} 年、WACC {fmt_pct(assum.get('wacc'))}、"
        f"永续增长 {fmt_pct(assum.get('terminal_growth'))}、显性期增长 {fmt_pct(assum.get('first_stage_growth'))}。"
    )

    if intrinsic is not None and price is not None:
        paragraphs.append(
            f"DCF 给出每股内在价值约 {fmt_num(intrinsic)} 元，当前价 {fmt_num(price)} 元，"
            f"安全边际 {fmt_pct(mos)}。"
        )
    elif intrinsic is not None:
        paragraphs.append(f"DCF 给出每股内在价值约 {fmt_num(intrinsic)} 元，但缺少可比当前价，安全边际暂无法计算。")
    else:
        paragraphs.append("因基期自由现金流或股本等数据不足，未能算出可靠的每股内在价值。")

    if relative:
        paragraphs.append(
            f"相对估值方面：历史判定为「{relative.history_verdict}」，"
            f"同业判定为「{relative.peer_verdict}」，总体「{relative.overall}」。"
        )

    paragraphs.append(f"综合提示：{verdict or '数据不足，无法定论'}。以上仅为基于公开财报与行情的量化测算，不构成投资建议。")

    if notes:
        paragraphs.append("备注：" + "；".join(notes[:5]))
    if errors:
        paragraphs.append("数据缺口：" + "；".join(errors[:5]))

    text = "\n\n".join(paragraphs)
    # 总结不是计算步骤：只给散文段 + 关键数字快照，不再重复公式教学
    snapshot = md_table(
        ["项目", "结果"],
        [
            ["每股内在价值", f"{fmt_num(intrinsic)} 元"],
            ["当前价", f"{fmt_num(price)} 元"],
            ["安全边际", fmt_pct(mos)],
            ["相对估值", (relative.overall if relative else None) or "—"],
            ["综合结论", verdict or "数据不足"],
        ],
    )
    return {
        "key": "summary",
        "no": 0,
        "name": "总结",
        "raw": "",
        "formulas": [],
        "results": snapshot,
        "conclusions": [verdict or "数据不足，无法定论"],
        "text": text,
        "paragraphs": paragraphs,
    }


def build_valuation_report(
    *,
    code: str,
    name: str = "",
    dcf: DcfResult | None = None,
    relative: RelativeResult | None = None,
    metrics: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    annual_series: list[dict[str, Any]] | None = None,
    margin_of_safety_pct: float | None = None,
    verdict: str = "",
    notes: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """组装逐步报告：steps + summary。"""
    steps = [
        _step_fcf_base(dcf, metrics),
        _step_growth(dcf, annual_series),
        _step_explicit(dcf),
        _step_terminal(dcf),
        _step_equity(dcf, metrics, profile),
        _step_history(relative),
        _step_peers(relative),
        _step_margin(dcf, relative, margin_of_safety_pct, verdict),
    ]
    summary = _build_summary(
        code=code,
        name=name,
        dcf=dcf,
        relative=relative,
        margin_of_safety_pct=margin_of_safety_pct,
        verdict=verdict,
        notes=list(notes or []),
        errors=list(errors or []),
    )
    return {"steps": steps, "summary": summary}
