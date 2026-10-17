"""张新民「八看」：八看方法 + 汇总方法。

每一个 ``view_*`` 方法对应一「看」，返回结构化结果；``build_summary`` 汇总八看出具综合诊断。
"""

from __future__ import annotations

from typing import Any, Callable

from company.analysis.financialreport._common import (
    fmt_num,
    fmt_pct,
    fmt_x,
    fmt_yi,
    md_table,
    period_label,
    to_float,
    yoy,
)
from company.analysis.financialreport._fields import (
    COGS_FIELDS,
    NET_PROFIT_FIELDS,
    OCF_FIELDS,
    REVENUE_FIELDS,
    TOTAL_ASSETS_FIELDS,
    TOTAL_EQUITY_FIELDS,
    TOTAL_LIAB_FIELDS,
)
from company.analysis.financialreport.metrics import (
    cash_quality,
    classify_assets,
    classify_liabilities,
    competitiveness,
    core_profit,
    cost_structure,
    grade,
    operating_cash,
    revenue,
    strategy_type,
    value_parts,
)

VIEW_NAMES = {
    "strategy": "一看：战略——资源配置揭示什么？",
    "operating": "二看：经营资产管理与竞争力",
    "profit": "三看：效益与质量（核心利润视角）",
    "value": "四看：价值创造",
    "cost": "五看：成本决定机制",
    "quality": "六看：财务状况质量",
    "risk": "七看：风险",
    "outlook": "八看：前景",
}


def _raw_cell(row: dict[str, Any], getter: Any) -> str:
    if callable(getter):
        return str(getter(row))
    if isinstance(getter, (list, tuple)):
        return fmt_yi(to_float(_pick(row, *getter)))
    return fmt_yi(to_float(_pick(row, getter)))


def _raw_md(rows: list[dict[str, Any]], columns: list[tuple[str, Any]], *, limit: int | None = None) -> str:
    """原始数据：[行=科目，列=报告期]，报告期按时间从小到大。"""
    cap = 8 if limit is None else limit
    view = list(reversed(rows[:cap]))
    header = ["项目"] + [period_label(row) for row in view]
    body: list[list[str]] = [
        [name] + [_raw_cell(row, getter) for row in view]
        for name, getter in columns
    ]
    return md_table(header, body)


def _results_table(headers: list[str], rows: list[list[str]]) -> str:
    """计算结果：[行=指标，列=报告期]，报告期按时间从小到大。

    ``rows`` 与 ``series`` 同序（最新在前），首列为报告期标签。
    """
    asc = list(reversed(rows))
    header = ["指标"] + [row[0] for row in asc]
    body: list[list[str]] = [
        [headers[j]] + [row[j] for row in asc]
        for j in range(1, len(headers))
    ]
    return md_table(header, body)


def _pick(row: dict[str, Any], *keys: str) -> Any:
    from company.analysis.financialreport._common import pick

    return pick(row, *keys)


def _pct_col(*keys: str):
    def _fn(row: dict[str, Any]) -> str:
        return fmt_pct(to_float(_pick(row, *keys)))

    return _fn


def _formula_dict(item: Any) -> dict[str, str]:
    """把公式条目（dict 或 tuple）规整为带「含义/怎么看」的结构。"""
    if isinstance(item, dict):
        return {
            "name": item.get("name", ""),
            "formula": item.get("formula", ""),
            "meaning": item.get("meaning", ""),
            "reading": item.get("reading", ""),
        }
    return {"name": item[0], "formula": item[1], "meaning": "", "reading": ""}


def _formula_md(formulas: list) -> str:
    if not formulas:
        return "（本节无二次加工公式）"
    lines: list[str] = []
    for item in formulas:
        f = _formula_dict(item)
        lines.append(f"- **{f['name']}**：{f['formula']}")
        if f["meaning"]:
            lines.append(f"  - 含义：{f['meaning']}")
        if f["reading"]:
            lines.append(f"  - 怎么看：{f['reading']}")
    return "\n".join(lines)


def _step(raw: str, formulas: list, results: str, conc: list[str]) -> str:
    formula_md = _formula_md(formulas)
    items = [item for item in (conc or []) if item]
    raw_text = (raw or "").strip()
    results_text = (results or "").strip()
    lines = []
    if results_text:
        lines += ["#### 计算结果", "", results_text, ""]
    lines += ["#### 计算公式", "", formula_md, ""]
    if raw_text:
        lines += ["#### 原始数据", "", raw_text, ""]
    if items:
        lines += ["#### 结论", "", "\n".join(f"- {item}" for item in items)]
    return "\n".join(lines)


def _yi(value: Any) -> float | None:
    n = to_float(value)
    return n / 1e8 if n is not None else None


def _two_gold_ratio(row: dict[str, Any]) -> float | None:
    a = classify_assets(row)
    total = a.get("total_assets") or 0
    if not total or not a.get("two_gold"):
        return None
    return a["two_gold"] / total * 100


def _series(
    rows: list[dict[str, Any]],
    metrics: list[tuple[str, str, "Callable[[dict[str, Any]], Any]"]],
) -> dict[str, Any]:
    """把逐期指标整理成可供前端画时间轴折线图的结构。

    ``rows`` 为最新在前的同口径序列；返回按时间正序（旧→新）的 ``periods`` 与各指标 ``values``。
    """
    chrono = list(reversed(rows))
    return {
        "periods": [period_label(row) for row in chrono],
        "metrics": [
            {
                "label": label,
                "unit": unit,
                "values": [fn(row) for row in chrono],
            }
            for label, unit, fn in metrics
        ],
    }


def _view(
    key: str,
    no: int,
    raw: str,
    formulas: list[tuple[str, str]],
    results: str,
    conc: list[str],
    metrics: dict[str, Any] | None = None,
    series: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items = [item for item in (conc or []) if item]
    return {
        "key": key,
        "no": no,
        "name": VIEW_NAMES[key],
        "raw": (raw or "").strip(),
        "formulas": [_formula_dict(item) for item in (formulas or [])],
        "results": (results or "").strip(),
        "table": results,
        "series": series if series is not None else {"periods": [], "metrics": []},
        "metrics": metrics if metrics is not None else {},
        "conclusions": items,
        "text": _step(raw, formulas, results, items),
    }


def view_strategy(series: list[dict[str, Any]]) -> dict[str, Any]:
    """一看：战略——经营性/投资性资产配置与战略类型。"""
    latest, prev = series[0], (series[1] if len(series) > 1 else None)
    assets = classify_assets(latest)
    strategy = strategy_type(latest, prev)

    raw = _raw_md(
        series,
        [
            ("货币资金", "MONETARYFUNDS"),
            ("应收票据", "NOTE_RECE"),
            ("应收账款", "ACCOUNTS_RECE"),
            ("预付款项", "PREPAYMENT"),
            ("存货", "INVENTORY"),
            ("固定资产", "FIXED_ASSET"),
            ("在建工程", "CIP"),
            ("无形资产", "INTANGIBLE_ASSET"),
            ("长期股权投资", "LONG_EQUITY_INVEST"),
            ("商誉", "GOODWILL"),
            ("投资性房地产", "INVEST_REALESTATE"),
            ("交易性金融资产", "TRADE_FINASSET_NOTFVTPL"),
        ],
    )
    rows: list[list[str]] = []
    for i, row in enumerate(series[:8]):
        prev_row = series[i + 1] if i + 1 < len(series) else None
        a = classify_assets(row)
        st = strategy_type(row, prev_row)
        rows.append(
            [
                period_label(row),
                fmt_yi(a["operating_assets"]),
                fmt_pct(a["operating_ratio"]),
                fmt_yi(a["investing_assets"]),
                fmt_pct(a["investing_ratio"]),
                st.get("strategy_type") or "—",
            ]
        )
    results = _results_table(
        ["报告期", "经营性资产", "经营性资产占比", "投资性资产", "投资性资产占比", "战略类型"],
        rows,
    )
    conc: list[str] = []
    formulas = [
        (
            "经营性资产",
            "货币资金、应收、预付、存货、固定资产、在建工程、无形资产等经营占用项合计",
            f"{period_label(latest)}经营性资产 {fmt_yi(assets.get('operating_assets'))}",
        ),
        (
            "投资性资产",
            "长期股权投资、商誉、金融资产、投资性房地产等投资经营项合计",
            f"投资性资产 {fmt_yi(assets.get('investing_assets'))}",
        ),
        ("经营性资产占比", "经营性资产 ÷ 总资产", f"占总资产 {fmt_pct(strategy.get('operating_asset_ratio'))}"),
        ("投资性资产占比", "投资性资产 ÷ 总资产", f"占总资产 {fmt_pct(strategy.get('investing_asset_ratio'))}"),
        (
            "战略类型",
            "投资占比>35%且投资增速>经营增速→投资主导；经营占比>65%→经营主导；否则混合",
            f"本期判定为 {strategy.get('strategy_type')}",
        ),
    ]
    chart = _series(
        series,
        [
            ("经营性资产占比", "pct", lambda r: classify_assets(r)["operating_ratio"]),
            ("投资性资产占比", "pct", lambda r: classify_assets(r)["investing_ratio"]),
            ("固定资产", "yi", lambda r: _yi(classify_assets(r)["fixed_asset"])),
            ("商誉", "yi", lambda r: _yi(classify_assets(r)["goodwill"])),
        ],
    )
    return _view("strategy", 1, raw, formulas, results, conc, {"assets": assets, "strategy": strategy}, chart)


def view_operating(series: list[dict[str, Any]]) -> dict[str, Any]:
    """二看：经营资产管理与竞争力（两头吃、周转）。"""
    raw = _raw_md(
        series,
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
    for row in series[:8]:
        c = competitiveness(row)
        a = classify_assets(row)
        rows.append(
            [
                period_label(row),
                fmt_x(c["two_ends_index"]),
                (fmt_num(c["inventory_turnover_days"], 0) + "天") if c["inventory_turnover_days"] else "—",
                (fmt_num(c["receivable_turnover_days"], 0) + "天") if c["receivable_turnover_days"] else "—",
                fmt_x(c["fixed_asset_turnover"]),
                fmt_yi(a["two_gold"]),
                fmt_pct(_two_gold_ratio(row)),
                fmt_pct(core_profit(row)["gross_margin"]),
            ]
        )
    results = _results_table(
        ["报告期", "两头吃指数", "存货周转天数", "应收周转天数", "固定资产周转", "两金合计", "两金占比", "毛利率"],
        rows,
    )
    conc: list[str] = []
    formulas = [
        {
            "name": "两头吃指数",
            "formula": "(应付账款 + 预收款项/合同负债) ÷ (应收账款 + 预付款项)",
            "meaning": "衡量公司在产业链上的话语权：分子是占用上游供应商（应付账款）与下游客户（预收/合同负债）的资金，分母是被上游（预付款项）与下游（应收账款）占用的资金，即「我占用别人的钱」与「别人占用我的钱」之比。",
            "reading": ">1 表示两头吃、占款能力强，能靠上下游免费融资；≈1 为中性；<1 表示资金被上下游占用。评级口径：≥1.2 优、≥0.8 中，否则差。",
        },
        {
            "name": "存货周转天数",
            "formula": "365 × 存货 ÷ 营业成本",
            "meaning": "存货从入库到卖出平均要压多少天。365 ÷（营业成本 ÷ 存货），即一年天数除以存货一年周转的次数。用营业成本作分母，是因为存货按成本记账、售出时结转营业成本，口径匹配。",
            "reading": "越短越好，卖得快、资金占用少；越长约危险，可能是滞销或备货过度。无绝对标准，主要与自身历史及同行对比，并留意是否靠压货推高收入。",
        },
        {
            "name": "应收周转天数",
            "formula": "365 × 应收账款 ÷ 营业收入",
            "meaning": "销售商品从确认收入到收回货款平均要等多少天。365 ×（应收账款 ÷ 营业收入），分母用营业收入（含税口径），与应收账款相匹配。",
            "reading": "越短越好，回款快、坏账风险低；越长越差。含金量预警：当「应收增速」明显快于「营收增速」（应收增速 > 营收增速 × 1.5，且营收增速 > 0）时，说明收入可能靠放宽账期换来，含金量存疑。两个增速的含义——① 应收增速：应收账款的同比增长率 =（本期应收账款 − 上期应收账款）÷ 上期应收账款；② 营收增速：营业收入的同比增长率 =（本期营业收入 − 上期营业收入）÷ 上期营业收入。正常情况下两者应大致同步；若应收涨得远快于收入，意味着新增收入大部分没有收回现金、而是变成了客户欠款，多因放宽赊销条件堆高销量，这类增长「虚胖」且不可持续（可能演化为坏账）。注意：这只是预警信号而非定论，需结合应收账龄结构、前五大欠款客户、坏账准备计提及季节性等因素进一步核实。",
        },
        {
            "name": "固定资产周转",
            "formula": "营业收入 ÷ 固定资产",
            "meaning": "每 1 元固定资产一年能产出多少元营业收入，反映厂房、设备等长期资产的产出效率。",
            "reading": "越高越好，说明设备利用充分；越低可能是产能闲置或项目刚投建未达产。适合制造、电力等重资产行业，轻资产公司分母过小易虚高失真。",
        },
        {
            "name": "两金合计",
            "formula": "应收账款 + 存货",
            "meaning": "应收账款与存货之和。「两金」是财务分析中对这两项最易占压资金、最易出问题的资产的俗称，合计即经营中被占用的「重头」资金。",
            "reading": "本身只反映规模（多少亿），不能单独下结论，需配合「两金占比」看。数值越大，说明越多资金卡在没收回的货款和没卖出的货上。",
        },
        {
            "name": "两金占比",
            "formula": "两金合计 ÷ 总资产",
            "meaning": "（应收账款 + 存货）÷ 总资产，衡量经营占用资金在全部资产中的分量。",
            "reading": "越低越稳健；>40% 判定为占用偏高，意味着回款与去库存压力大、资金易紧张。需结合行业特性与历史趋势判断。",
        },
        {
            "name": "毛利率",
            "formula": "(营业收入 − 营业成本) ÷ 营业收入",
            "meaning": "每 1 元收入扣除直接成本后剩余的比例，优先取财报披露值，缺省时现算。",
            "reading": "越高越好，说明产品有定价权；应与两头吃指数一起看，高毛利 + 高两头吃是强势公司的典型特征。关注趋势，下滑常意味着竞争加剧或成本失控。",
        },
    ]
    chart = _series(
        series,
        [
            ("两头吃指数", "x", lambda r: competitiveness(r)["two_ends_index"]),
            ("存货周转天数", "day", lambda r: competitiveness(r)["inventory_turnover_days"]),
            ("应收周转天数", "day", lambda r: competitiveness(r)["receivable_turnover_days"]),
            ("固定资产周转", "x", lambda r: competitiveness(r)["fixed_asset_turnover"]),
            ("两金占比", "pct", _two_gold_ratio),
            ("毛利率", "pct", lambda r: core_profit(r)["gross_margin"]),
        ],
    )
    return _view("operating", 2, raw, formulas, results, conc, {"competitiveness": competitiveness(series[0])}, chart)


def view_profit(series: list[dict[str, Any]]) -> dict[str, Any]:
    """三看：效益与质量（核心利润视角）。"""
    raw = _raw_md(
        series,
        [
            ("营业收入", REVENUE_FIELDS),
            ("营业成本", COGS_FIELDS),
            ("税金及附加", ("OPERATE_TAX_ADD", "OPERATE_TAX")),
            ("销售费用", "SALE_EXPENSE"),
            ("管理费用", "MANAGE_EXPENSE"),
            ("研发费用", "RESEARCH_EXPENSE"),
            ("财务费用", "FINANCE_EXPENSE"),
            ("归母净利润", NET_PROFIT_FIELDS),
            ("扣非净利润", ("KCFJCXSYJLR", "DEDUCT_PARENT_NETPROFIT")),
        ],
    )
    rows: list[list[str]] = []
    for row in series[:8]:
        p = core_profit(row)
        rows.append(
            [
                period_label(row),
                fmt_yi(p["core_profit"]),
                fmt_pct(p["core_margin"]),
                fmt_yi(p["non_core_profit"]),
                fmt_pct(p["deduct_ratio"]),
            ]
        )
    results = _results_table(
        ["报告期", "核心利润", "核心利润率", "非核心损益", "扣非占比"],
        rows,
    )
    conc: list[str] = []
    formulas = [
        {
            "name": "核心利润",
            "formula": "营业收入 − 营业成本 − 税金及附加 − 销售/管理/研发/财务费用",
            "meaning": "衡量公司靠卖自己的产品、服务本身赚了多少钱：只扣与主业经营直接相关的成本、税金和期间费用，是主业自身的盈利。特点是「只算主业」——投资收益、公允价值变动、资产处置、政府补贴等非日常经营所得一律不计入。",
            "reading": "越大越好，说明主营业务自身盈利能力强。若核心利润低甚至为负、而归母净利润却很高，说明利润主要靠非经营项目撑着，质量差、不可持续，需高度警惕。应与归母净利润对照看。",
        },
        {
            "name": "核心利润率",
            "formula": "核心利润 ÷ 营业收入",
            "meaning": "每 1 元营业收入中，扣除各项经营成本费用后真正剩下的比例，反映主营业务的赚钱效率。",
            "reading": "越高越好，说明主营盈利质量高、抗风险强。行业差异大（重资产、低毛利行业天然偏低），主要看自身趋势：持续下滑往往意味着竞争加剧或成本失控。",
        },
        {
            "name": "非核心损益",
            "formula": "归母净利润 − 核心利润",
            "meaning": "净利润中不由主营业务贡献、而来自投资收益、政府补贴、资产处置、公允价值变动等项目的那部分。",
            "reading": "绝对值越大，说明利润越依赖非主营因素、稳定性越差：为正代表靠「外快」增厚利润，为负代表主营被非经营项目拖累。长期看越小越好（利润越纯粹）。注意核心利润与净利润口径不完全一致，这只是粗略的「非核心」度量。",
        },
        {
            "name": "扣非占比",
            "formula": "扣非净利润 ÷ 归母净利润",
            "meaning": "扣非净利润（扣除政府补贴、资产处置、公允价值变动等一次性、非经常性损益后的净利润）占归母净利润的比例，衡量利润的「经常性」与真实性。",
            "reading": "越高越好，接近或超过 100% 说明利润主要来自经常性经营，质量高；低于 70% 说明利润中相当一部分来自一次性项目，持续性差（代码即以此为预警阈值）。超过 100% 也可能是非经常性亏损拖累了净利润。",
        },
    ]
    chart = _series(
        series,
        [
            ("营业收入", "yi", lambda r: _yi(revenue(r))),
            ("核心利润", "yi", lambda r: _yi(core_profit(r)["core_profit"])),
            ("核心利润率", "pct", lambda r: core_profit(r)["core_margin"]),
            ("扣非占比", "pct", lambda r: core_profit(r)["deduct_ratio"]),
        ],
    )
    return _view("profit", 3, raw, formulas, results, conc, {"profit": core_profit(series[0])}, chart)


def view_value(series: list[dict[str, Any]]) -> dict[str, Any]:
    """四看：价值创造（ROE/ROA + 杜邦拆解）。"""
    raw = _raw_md(
        series,
        [
            ("披露ROE", _pct_col("ROEJQ", "WEIGHTAVG_ROE")),
            ("披露ROA", _pct_col("ZZCJLL")),
            ("披露净利率", _pct_col("XSJLL")),
            ("营业收入", REVENUE_FIELDS),
            ("归母净利润", NET_PROFIT_FIELDS),
            ("总资产", TOTAL_ASSETS_FIELDS),
            ("净资产", TOTAL_EQUITY_FIELDS),
        ],
    )
    rows: list[list[str]] = []
    for row in series[:8]:
        p = core_profit(row)
        d = value_parts(row, p)
        rows.append(
            [
                period_label(row),
                fmt_pct(p["roe"]),
                fmt_pct(d["roa"]),
                fmt_pct(p["net_margin"]),
                fmt_x(d["asset_turnover"]),
                fmt_x(d["equity_multiplier"]),
            ]
        )
    results = _results_table(
        ["报告期", "ROE", "ROA", "净利率", "资产周转", "权益乘数"],
        rows,
    )
    conc: list[str] = []
    formulas = [
        {
            "name": "ROE",
            "formula": "归母净利润 ÷ 净资产（优先取财报披露值）",
            "meaning": "股东每投入 1 元净资产，一年能赚回多少净利润，是衡量股东回报的核心指标。",
            "reading": "越高越好：≥15% 优、≥8% 中，否则差。看趋势比看单期更重要，持续下滑说明赚钱能力在减弱；突然跳升要看是否靠高杠杆或一次性收益。",
        },
        {
            "name": "ROA",
            "formula": "归母净利润 ÷ 总资产（优先取财报披露的总资产净利率）",
            "meaning": "公司全部资产（不论股东出钱还是借钱）每 1 元一年能赚多少净利润，衡量整体资产的赚钱效率，不受融资结构影响。",
            "reading": "越高越好，说明同样规模的资产产出更多利润。主要看趋势和同行对比；ROA 远低于 ROE，说明 ROE 主要靠加杠杆撑起来。",
        },
        {
            "name": "净利率",
            "formula": "归母净利润 ÷ 营业收入（优先取财报披露值）",
            "meaning": "每 1 元营业收入最终能剩下多少净利润，衡量整体盈利空间，是收入转化为利润的效率。",
            "reading": "越高越好，说明产品有定价权或费用控制好。看趋势：下滑常因竞争加剧或成本费用上升；净利率高但 ROE 低，多半是资产周转慢或杠杆低。",
        },
        {
            "name": "资产周转",
            "formula": "营业收入 ÷ 总资产",
            "meaning": "每 1 元总资产一年能周转出多少元营业收入，衡量全部资产的营运效率、用得多快。",
            "reading": "越高越好，说明资产利用充分、周转快；越低说明资产闲置或效率低。行业差异大（零售/快消高、重资产低），主要看趋势和同行。它是杜邦分解里 ROE 的驱动项之一。",
        },
        {
            "name": "权益乘数",
            "formula": "总资产 ÷ 净资产",
            "meaning": "总资产是净资产的多少倍，反映财务杠杆（用负债把资产放大的倍数）。",
            "reading": "越高说明杠杆越高、负债越多，股东以小博大但偿债风险也大；越低越稳健。它是杜邦分解里放大 ROE 的一环，但靠高杠杆撑起来的高 ROE 质量偏低、风险偏高，需与负债率一并看。",
        },
    ]
    chart = _series(
        series,
        [
            ("ROE", "pct", lambda r: core_profit(r)["roe"]),
            ("ROA", "pct", lambda r: value_parts(r, core_profit(r))["roa"]),
            ("资产周转", "x", lambda r: value_parts(r, core_profit(r))["asset_turnover"]),
            ("权益乘数", "x", lambda r: value_parts(r, core_profit(r))["equity_multiplier"]),
        ],
    )
    return _view("value", 4, raw, formulas, results, conc, {"value": value_parts(series[0], core_profit(series[0]))}, chart)


def view_cost(series: list[dict[str, Any]]) -> dict[str, Any]:
    """五看：成本决定机制（成本率、费用率）。"""
    raw = _raw_md(
        series,
        [
            ("营业收入", REVENUE_FIELDS),
            ("营业成本", COGS_FIELDS),
            ("销售费用", "SALE_EXPENSE"),
            ("管理费用", "MANAGE_EXPENSE"),
            ("研发费用", "RESEARCH_EXPENSE"),
            ("财务费用", "FINANCE_EXPENSE"),
        ],
    )
    rows: list[list[str]] = []
    for row in series[:8]:
        rev = revenue(row)
        if not rev:
            continue
        cs = cost_structure(row).get("rates", {})
        rows.append(
            [
                period_label(row),
                fmt_pct(cs.get("营业成本率")),
                fmt_pct(cs.get("销售费用率")),
                fmt_pct(cs.get("管理费用率")),
                fmt_pct(cs.get("研发费用率")),
                fmt_pct(cs.get("财务费用率")),
            ]
        )
    results = _results_table(
        ["报告期", "营业成本率", "销售费用率", "管理费用率", "研发费用率", "财务费用率"],
        rows,
    )
    conc: list[str] = []
    cr = cost_structure(next((row for row in series if revenue(row)), series[0])).get("rates", {})
    formulas = [
        ("营业成本率", "营业成本 ÷ 营业收入", f"{period_label(series[0])}营业成本率 {fmt_pct(cr.get('营业成本率'))}"),
        (
            "销售/管理/研发/财务费用率",
            "对应期间费用 ÷ 营业收入",
            f"销售 {fmt_pct(cr.get('销售费用率'))}、管理 {fmt_pct(cr.get('管理费用率'))}、"
            f"研发 {fmt_pct(cr.get('研发费用率'))}、财务 {fmt_pct(cr.get('财务费用率'))}",
        ),
    ]
    chart = _series(
        series,
        [
            ("营业成本率", "pct", lambda r: cost_structure(r).get("rates", {}).get("营业成本率")),
            ("销售费用率", "pct", lambda r: cost_structure(r).get("rates", {}).get("销售费用率")),
            ("管理费用率", "pct", lambda r: cost_structure(r).get("rates", {}).get("管理费用率")),
            ("研发费用率", "pct", lambda r: cost_structure(r).get("rates", {}).get("研发费用率")),
            ("财务费用率", "pct", lambda r: cost_structure(r).get("rates", {}).get("财务费用率")),
        ],
    )
    return _view("cost", 5, raw, formulas, results, conc, {"cost": cost_structure(series[0])}, chart)


def view_quality(series: list[dict[str, Any]]) -> dict[str, Any]:
    """六看：财务状况质量（资产 + 负债 + 现金流含金量）。"""
    latest, prev = series[0], (series[1] if len(series) > 1 else None)
    liab_raw = _raw_md(
        series,
        [
            ("短期借款", "SHORT_LOAN"),
            ("长期借款", "LONG_LOAN"),
            ("应付账款", "ACCOUNTS_PAYABLE"),
            ("预收/合同负债", ("ADVANCE_RECEIVABLES", "CONTRACT_LIAB")),
            ("负债合计", TOTAL_LIAB_FIELDS),
        ],
    )
    cash_raw = _raw_md(
        series,
        [
            ("经营现金流", OCF_FIELDS),
            ("投资现金流", ("NETCASH_INVEST_PK", "NETCASH_INVEST")),
            ("筹资现金流", ("NETCASH_FINANCE_PK", "NETCASH_FINANCE")),
            ("销售商品收现", "SALES_SERVICES"),
            ("归母净利润", NET_PROFIT_FIELDS),
        ],
    )

    liab_rows: list[list[str]] = []
    for row in series[:8]:
        li = classify_liabilities(row)
        liab_rows.append(
            [
                period_label(row),
                fmt_yi(li["financial_liabilities"]),
                fmt_pct(li["financial_ratio"]),
                fmt_yi(li["operating_liabilities"]),
                fmt_pct(li["operating_ratio"]),
            ]
        )
    liab_results = _results_table(
        ["报告期", "金融性负债", "金融性负债占比", "经营性负债", "经营性负债占比"],
        liab_rows,
    )

    cash_rows: list[list[str]] = []
    for i, row in enumerate(series[:8]):
        p = series[i + 1] if i + 1 < len(series) else None
        c = cash_quality(row, p)
        cash_rows.append(
            [
                period_label(row),
                fmt_yi(c["fcf"]),
                fmt_pct(c["ocf_core_ratio"]),
                fmt_pct(c["ocf_profit_ratio"]),
                fmt_pct(c["cash_collection_ratio"]),
                c["cashflow_mode"],
            ]
        )
    cash_results = _results_table(
        ["报告期", "自由现金流", "OCF/核心利润", "OCF/净利润", "销售收现比", "现金流模式"],
        cash_rows,
    )

    raw = "\n\n".join(["**负债结构**\n\n" + liab_raw, "**现金流质量**\n\n" + cash_raw])
    results = "\n\n".join(["**负债结构**\n\n" + liab_results, "**现金流质量**\n\n" + cash_results])

    li = classify_liabilities(latest)
    c = cash_quality(latest, prev)
    bullets: list[str] = []
    formulas = [
        {
            "name": "金融性负债",
            "formula": "短期借款 + 长期借款 + 应付债券 + 租赁负债 + 一年内到期非流动负债",
            "meaning": "公司靠付利息借来的钱（有息负债），是需要还本付息、有资金成本的负债。",
            "reading": "绝对额越大，利息负担和偿债压力越大。要结合占比看：只看金额不看结构没有意义。",
        },
        {
            "name": "金融性负债占比",
            "formula": "金融性负债 ÷ 负债合计",
            "meaning": "有息负债在全部负债里的比重，衡量公司对「借钱」的依赖程度。",
            "reading": "越低越稳健；超过 60% 说明对有息债务依赖偏高，利息侵蚀利润、资金链偏紧，需警惕偿债风险。",
        },
        {
            "name": "经营性负债",
            "formula": "应付账款 + 应付票据 + 预收/合同负债 + 应付职工薪酬 + 应交税费 + 其他应付款",
            "meaning": "做生意自然占用上下游的钱（欠供应商的货款、客户预付的货款、欠员工和税务的钱），不用付利息，是「免费」的负债。",
            "reading": "经营性负债高于金融性负债是好事，说明更多靠商业信用而非借钱经营，体现产业链地位。",
        },
        {
            "name": "经营性负债占比",
            "formula": "经营性负债 ÷ 负债合计",
            "meaning": "免费占用的商业信用在全部负债里的比重，与金融性负债占比互为镜像。",
            "reading": "越高越好，说明负债里大部分是无成本的占款；与金融性负债占比对照看，两者此消彼长。",
        },
        {
            "name": "自由现金流",
            "formula": "优先取财报披露的企业自由现金流（FCFF，企业自由现金流量）；缺省时按 经营活动现金流量净额（OCF） − 购建固定资产等资本开支估算",
            "meaning": "经营活动现金流量净额（OCF，指经营活动产生的现金流量净额，即做生意实际收到的净现金）扣掉维持和扩大生产必须花的资本开支后，真正可以自由支配的钱。",
            "reading": "越大越好，持续为正说明公司自己能造血、还能剩钱；长期为负说明靠融资续命。其中 FCFF 是企业自由现金流量的英文缩写，指归全体出资人（股东加债权人）可支配的现金。",
        },
        {
            "name": "OCF/核心利润",
            "formula": "经营活动现金流量净额（OCF） ÷ 核心利润",
            "meaning": "主业赚的利润里，有多少变成了真金白银收回来。OCF 是经营活动现金流量净额的缩写，即经营收到的净现金。",
            "reading": "越高越好：≥100% 优（利润足额变现）、≥80% 中，否则差。长期低于 80% 说明利润是账面富贵，含金量低。",
        },
        {
            "name": "OCF/净利润",
            "formula": "经营活动现金流量净额（OCF） ÷ 归母净利润",
            "meaning": "最终净利润里有多少收回了现金，和上一条口径类似，只是分母换成归母净利润（包含非经常损益的最终利润）。",
            "reading": "越高越好，低于 80% 警示：净利润看着高但没收到钱，可能是赊销堆出来的，需结合应收增速一起看。",
        },
        {
            "name": "销售收现比",
            "formula": "销售商品提供劳务收到的现金 ÷ 营业收入",
            "meaning": "每 1 元营业收入，当期实际收回了多少现金，衡量销售回款的及时性。",
            "reading": "越接近或超过 100% 越好，说明现款现货、回款及时；明显低于 100% 说明大量销售挂在应收账款上，回款慢。",
        },
        {
            "name": "现金流模式",
            "formula": "按经营活动现金流（OCF）、投资活动现金流、筹资活动现金流的正负组合判定：经营为正且投资为负→造血型；经营为负且投资为正→输血型；经营为负且靠筹资为正→融资依赖型；其余→混合型",
            "meaning": "把经营、投资、筹资三张现金流量表的正负摆在一起，看公司处在「自己造血」还是「靠外部输血」的阶段。",
            "reading": "造血型最健康（自己赚钱供投资）；输血型和融资依赖型要警惕，说明经营不产生现金、靠卖资产或借钱维持；混合型需结合具体数字看是哪一边主导。",
        },
    ]
    chart = _series(
        series,
        [
            ("金融性负债占比", "pct", lambda r: classify_liabilities(r)["financial_ratio"]),
            ("经营性负债占比", "pct", lambda r: classify_liabilities(r)["operating_ratio"]),
            ("经营现金流", "yi", lambda r: _yi(operating_cash(r))),
            ("OCF/核心利润", "pct", lambda r: cash_quality(r, None)["ocf_core_ratio"]),
            ("OCF/净利润", "pct", lambda r: cash_quality(r, None)["ocf_profit_ratio"]),
            ("销售收现比", "pct", lambda r: cash_quality(r, None)["cash_collection_ratio"]),
        ],
    )
    return _view("quality", 6, raw, formulas, results, bullets, {"liabilities": li, "cash": c}, chart)


def _risk_items(series: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """七看：8 项风险逐项判定，返回 (items, hit_count)，供七看与综合诊断共用。"""
    latest = series[0]
    prev = series[1] if len(series) > 1 else None
    a = classify_assets(latest)
    rl = classify_liabilities(latest)
    rp = core_profit(latest)
    rc = cash_quality(latest, prev)
    total = a.get("total_assets") or 0
    total_liab = to_float(_pick(latest, *TOTAL_LIAB_FIELDS))
    goodwill = a.get("goodwill")
    goodwill_ratio = goodwill / total * 100 if goodwill and total else None
    debt_ratio = total_liab / total * 100 if total_liab and total else None
    two_gold_ratio = _two_gold_ratio(latest)
    cash_val, short_loan = a.get("cash"), rl.get("short_loan")
    return _risk_threshold_items(a, rl, rp, rc, total, total_liab, goodwill)


def _risk_formulas() -> list:
    """七看 8 条判定规则（含含义/怎么看）。"""
    formulas = [
        {
            "name": "商誉占比",
            "formula": "商誉 ÷ 总资产，> 15% 触发警示",
            "meaning": "商誉是过去高价并购留下的溢价，本身不产生现金且无法变现，只能靠被并购公司持续赚钱来消化。",
            "reading": "超过 15% 说明资产里有相当一块是并购溢价，若被并购方业绩不达预期，一次减值就可能引发大额亏损。",
        },
        {
            "name": "存贷双高",
            "formula": "货币资金 > 短期借款 × 2 且短期借款 > 0 时触发警示",
            "meaning": "账上趴着大量现金，同时还借着不少短期借款——有钱却不还钱，资金配置反常。",
            "reading": "触发时要怀疑货币资金是否真实（是否被冻结、质押或造假），或借款另有用途，需结合现金流和附注核实。",
        },
        {
            "name": "资产负债率",
            "formula": "负债合计 ÷ 总资产，> 70% 触发警示",
            "meaning": "全部资产里有多少是借来的，衡量整体杠杆和偿债压力。",
            "reading": "超过 70% 说明高度依赖负债经营，利息负担重、抗风险能力弱；金融、地产等行业天然偏高，需结合行业看。",
        },
        {
            "name": "金融性负债占比",
            "formula": "金融性负债 ÷ 负债合计，> 60% 触发警示",
            "meaning": "有息负债在全部负债里的比重，衡量对借钱的依赖（六看已解释）。",
            "reading": "超过 60% 说明负债多半是要付利息的，财务费用侵蚀利润，资金链偏紧。",
        },
        {
            "name": "扣非占比",
            "formula": "扣非净利润 ÷ 归母净利润，< 70% 触发警示",
            "meaning": "利润里经常性经营贡献的成色（六看/三看已解释）。",
            "reading": "低于 70% 说明利润靠一次性项目撑着，持续性差，粉饰嫌疑需警惕。",
        },
        {
            "name": "利润含金量",
            "formula": "经营活动现金流量净额（OCF）÷ 净利润、OCF ÷ 核心利润，任一 < 80% 触发警示",
            "meaning": "赚的利润有没有变成真金白银收回来（六看已解释）。",
            "reading": "低于 80% 说明利润是账面富贵，大概率靠赊销堆出来，未来可能转为坏账或现金流断裂。",
        },
        {
            "name": "两金占比",
            "formula": "(应收账款 + 存货) ÷ 总资产，> 40% 触发警示",
            "meaning": "经营占用资金在全部资产里的分量（二看已解释）。",
            "reading": "超过 40% 说明大量资金压在没收回的货款和没卖出的货上，回款与去库存压力大。",
        },
        {
            "name": "三脱节",
            "formula": "应收/存货增速 > 营收增速 × 1.5，或核心利润增速 > 10% 但经营现金流增速 < 核心利润增速的一半时触发警示",
            "meaning": "收入、利润、现金流三者本该同步增长，脱节说明增长质量出了问题。",
            "reading": "触发说明收入可能是放宽账期换来的，或利润没变成现金，是财务造假和经营恶化的高发信号，需逐项核实。",
        },
    ]
    return formulas


def _risk_threshold_items(a, rl, rp, rc, total, total_liab, goodwill) -> tuple[list[dict[str, Any]], int]:
    """8 项风险逐项判定，返回 (items, hit_count)。"""
    goodwill_ratio = goodwill / total * 100 if goodwill and total else None
    debt_ratio = total_liab / total * 100 if total_liab and total else None
    two_gold = a.get("two_gold")
    two_gold_ratio = two_gold / total * 100 if two_gold and total else None
    cash_val, short_loan = a.get("cash"), rl.get("short_loan")
    risk_items = [
        {
            "name": "商誉占比",
            "threshold": "> 15%",
            "value": fmt_pct(goodwill_ratio),
            "triggered": bool(goodwill_ratio is not None and goodwill_ratio > 15),
        },
        {
            "name": "存贷双高",
            "threshold": "货币资金 > 短期借款 × 2",
            "value": f"货币资金 {fmt_yi(cash_val)} / 短期借款 {fmt_yi(short_loan)}",
            "triggered": bool(cash_val and short_loan and cash_val > short_loan * 2 and short_loan > 0),
        },
        {
            "name": "资产负债率",
            "threshold": "> 70%",
            "value": fmt_pct(debt_ratio),
            "triggered": bool(debt_ratio is not None and debt_ratio > 70),
        },
        {
            "name": "金融性负债占比",
            "threshold": "> 60%",
            "value": fmt_pct(rl.get("financial_ratio")),
            "triggered": bool(rl.get("financial_ratio") is not None and rl["financial_ratio"] > 60),
        },
        {
            "name": "扣非占比",
            "threshold": "< 70%",
            "value": fmt_pct(rp.get("deduct_ratio")),
            "triggered": bool(rp.get("deduct_ratio") is not None and rp["deduct_ratio"] < 70),
        },
        {
            "name": "利润含金量",
            "threshold": "OCF/净利润、OCF/核心利润 < 80%",
            "value": f"OCF/净利润 {fmt_pct(rc.get('ocf_profit_ratio'))}、OCF/核心利润 {fmt_pct(rc.get('ocf_core_ratio'))}",
            "triggered": bool(
                (rc.get("ocf_profit_ratio") is not None and rc["ocf_profit_ratio"] < 80)
                or (rc.get("ocf_core_ratio") is not None and rc["ocf_core_ratio"] < 80)
            ),
        },
        {
            "name": "两金占比",
            "threshold": "> 40%",
            "value": fmt_pct(two_gold_ratio),
            "triggered": bool(two_gold_ratio is not None and two_gold_ratio > 40),
        },
        {
            "name": "三脱节",
            "threshold": "增速背离",
            "value": "；".join(rc.get("disconnections") or []) or "未见脱节迹象",
            "triggered": bool(rc.get("disconnections")),
        },
    ]
    hit_count = sum(1 for item in risk_items if item["triggered"])
    return risk_items, hit_count


def view_risk(series: list[dict[str, Any]], flags: list[str]) -> dict[str, Any]:
    """七看：风险（规则引擎警示清单）。"""
    if flags:
        results = "\n".join(f"- {item}" for item in flags)
    else:
        results = "- 规则引擎未触发重大风险警示。"
    raw = ""
    conc: list[str] = []
    latest = series[0]
    risk_items, hit_count = _risk_items(series)
    formulas = _risk_formulas()
    view = _view("risk", 7, raw, formulas, results, conc, {"flags": flags})
    view["layout"] = "risk"
    view["metrics"] = {
        "flags": flags,
        "items": risk_items,
        "hit_count": hit_count,
        "total_count": len(risk_items),
        "latest_period": period_label(latest),
    }
    return view


def view_outlook(series: list[dict[str, Any]]) -> dict[str, Any]:
    """八看：前景（趋势与可持续性）。"""
    raw = _raw_md(
        series,
        [
            ("营业收入", REVENUE_FIELDS),
            ("核心利润", lambda r: fmt_yi(core_profit(r)["core_profit"])),
            ("经营现金流", OCF_FIELDS),
            ("经营性资产", lambda r: fmt_yi(classify_assets(r)["operating_assets"])),
            ("投资性资产", lambda r: fmt_yi(classify_assets(r)["investing_assets"])),
        ],
    )
    rows: list[list[str]] = []
    for i, row in enumerate(series):
        prev = series[i + 1] if i + 1 < len(series) else None
        a = classify_assets(row)
        prev_a = classify_assets(prev) if prev else {}
        p = core_profit(row)
        prev_p = core_profit(prev) if prev else {}
        op_yoy = yoy(a.get("operating_assets"), prev_a.get("operating_assets"))
        inv_yoy = yoy(a.get("investing_assets"), prev_a.get("investing_assets"))
        core_yoy = yoy(p.get("core_profit"), prev_p.get("core_profit"))
        ocf_yoy = yoy(operating_cash(row), operating_cash(prev) if prev else None)
        if op_yoy is None or inv_yoy is None:
            direction = "—"
        else:
            direction = "扩张" if op_yoy > 0 and inv_yoy > 0 else "收缩"
        if op_yoy is None or core_yoy is None or ocf_yoy is None:
            coherence = "—"
        else:
            coherence = "自洽" if op_yoy > 0 and core_yoy > 0 and ocf_yoy > 0 else "待观察"

        rows.append(
            [
                period_label(row),
                fmt_pct(yoy(revenue(row), revenue(prev) if prev else None)),
                fmt_pct(core_yoy),
                fmt_pct(ocf_yoy),
                fmt_pct(op_yoy),
                fmt_pct(inv_yoy),
                direction,
                coherence,
            ]
        )
    results = _results_table(
        ["报告期", "营收同比", "核心利润同比", "经营现金流同比", "经营性资产同比", "投资性资产同比", "扩张/收缩", "增长自洽"],
        rows,
    )
    conc: list[str] = []
    formulas = [
        {
            "name": "营收同比",
            "formula": "(本期营业收入 − 上期同口径营业收入) ÷ 上期同口径营业收入",
            "meaning": "营业收入相对上一期同口径报告的增长率，衡量销售规模扩张的速度。",
            "reading": "为正说明在扩张，为负说明在收缩。主要看趋势是否持续，以及是否跑赢同行；单期高增长要看基数是否过低。",
        },
        {
            "name": "核心利润同比",
            "formula": "(本期核心利润 − 上期同口径核心利润) ÷ 上期同口径核心利润",
            "meaning": "主业自身利润相对上一期同口径的增长率，衡量主业赚钱能力的提升速度。",
            "reading": "应与营收同比对照看：两者同向为正且幅度接近，增长最健康；利润增速远高于收入增速，要看是费用控制见效还是一次性因素。",
        },
        {
            "name": "经营现金流同比",
            "formula": "(本期经营活动现金流量净额 − 上期同口径) ÷ 上期同口径",
            "meaning": "经营收回的净现金相对上一期的增长率，衡量造血能力的提升速度。",
            "reading": "应与核心利润同比对照看：利润涨但现金不涨甚至下滑，说明利润没变现，增长质量打折（即三脱节中的一组）。",
        },
        {
            "name": "经营性资产同比",
            "formula": "(本期经营性资产 − 上期经营性资产) ÷ 上期经营性资产",
            "meaning": "投入经营的资产相对上一期的增长率，衡量经营投入的扩张速度。",
            "reading": "为正说明在加码经营投入；要与营收同比对照：资产涨得远快于收入，说明投入还没换来产出，效率待观察。",
        },
        {
            "name": "投资性资产同比",
            "formula": "(本期投资性资产 − 上期投资性资产) ÷ 上期投资性资产",
            "meaning": "投入投资的资产相对上一期的增长率，衡量对外投资扩张的速度。",
            "reading": "与经营性资产同比对照看：投资涨得远快于经营，说明战略重心在向外移，需警惕主业空心化。",
        },
        {
            "name": "扩张/收缩",
            "formula": "经营性资产同比与投资性资产同比同向为正 → 扩张，否则收缩",
            "meaning": "用经营和投资两类资产是否同时在增加，判断公司整体处在扩张还是收缩阶段。",
            "reading": "两类资产同增才是真扩张；一增一减说明在调结构；同减说明在收缩。结合营收同比看扩张有没有换来收入。",
        },
        {
            "name": "增长自洽",
            "formula": "经营性资产同比、核心利润同比、经营现金流同比三者同向为正 → 增长较自洽",
            "meaning": "投入在加码、利润在增长、现金在回流，三者同步才算高质量增长，任一掉队都说明链条有问题。",
            "reading": "三者同为正，增长自洽、可持续；否则（尤其利润涨但现金不涨）增长质量待观察，需回看三脱节是哪一节掉了队。",
        },
    ]
    chrono = list(reversed(series))

    def _yoy_metric(fn: Callable[[dict[str, Any]], Any]) -> list[float | None]:
        out: list[float | None] = []
        for i, row in enumerate(chrono):
            out.append(yoy(fn(row), fn(chrono[i - 1])) if i > 0 else None)
        return out

    chart = {
        "periods": [period_label(row) for row in chrono],
        "metrics": [
            {"label": "营收同比", "unit": "pct", "values": _yoy_metric(revenue)},
            {"label": "核心利润同比", "unit": "pct", "values": _yoy_metric(lambda r: core_profit(r)["core_profit"])},
            {"label": "经营现金流同比", "unit": "pct", "values": _yoy_metric(operating_cash)},
            {"label": "经营性资产同比", "unit": "pct", "values": _yoy_metric(lambda r: classify_assets(r)["operating_assets"])},
            {"label": "投资性资产同比", "unit": "pct", "values": _yoy_metric(lambda r: classify_assets(r)["investing_assets"])},
        ],
    }
    return _view("outlook", 8, raw, formulas, results, conc, {}, chart)


def build_summary(
    series: list[dict[str, Any]],
    bundle: dict[str, Any],
    *,
    coverage: str = "",
) -> dict[str, Any]:
    """汇总方法：把八看收敛成七个评分方面 + 综合诊断（战略方向不计分）。"""
    strategy = bundle.get("strategy") or {}
    profit = bundle.get("profit") or {}
    cash = bundle.get("cash") or {}
    comp = bundle.get("competitiveness") or {}
    cost = cost_structure(series[0]).get("rates", {}) if series else {}

    risk_items, risk_count = _risk_items(series) if series else ([], 0)
    hit_detail = "；".join(f"{item['name']}：{item['value']}" for item in risk_items if item["triggered"])

    expense_ratio = sum(
        (cost.get(k) or 0) for k in ("销售费用率", "管理费用率", "研发费用率", "财务费用率")
    )
    expense_ratio = expense_ratio if series and revenue(series[0]) else None

    def _trend(curr: float | None, prev: float | None, higher_is_better: bool = True) -> str:
        """与上一期同口径对比：变好 / 变差 / 持平 / —（缺数据）。"""
        if curr is None or prev is None:
            return "—"
        if curr == prev:
            return "持平"
        better = curr > prev if higher_is_better else curr < prev
        return "变好" if better else "变差"

    prev_row = series[1] if len(series) > 1 else None
    prev_comp = competitiveness(prev_row) if prev_row else {}
    prev_profit = core_profit(prev_row) if prev_row else {}
    prev_cash = (
        cash_quality(prev_row, series[2] if len(series) > 2 else None) if prev_row else {}
    )
    prev_cost = cost_structure(prev_row).get("rates", {}) if prev_row else {}
    prev_expense = (
        sum((prev_cost.get(k) or 0) for k in ("销售费用率", "管理费用率", "研发费用率", "财务费用率"))
        if prev_row and revenue(prev_row)
        else None
    )
    core_profit_val = profit.get("core_profit")
    prev_core_profit_val = prev_profit.get("core_profit")
    prev_roe = prev_profit.get("roe")
    prev_ocf_core = prev_cash.get("ocf_core_ratio")
    prev_two_ends = prev_comp.get("two_ends_index")

    latest = series[0] if series else {}
    prev = series[1] if len(series) > 1 else None
    core_vals = [core_profit(r).get("core_profit") for r in series]
    core_vals = [v for v in core_vals if v is not None]
    ocf_vals = [operating_cash(r) for r in series]
    ocf_vals = [v for v in ocf_vals if v is not None]
    rev_vals = [revenue(r) for r in series]
    rev_vals = [v for v in rev_vals if v is not None]

    def _multi_trend(vals: list) -> str:
        """最近几期报告来看：增长 / 减少 / 不变 / —（不足两期有效数据）。"""
        if len(vals) < 2:
            return "—"
        if vals[0] > vals[-1]:
            return "增长"
        if vals[0] < vals[-1]:
            return "减少"
        return "不变"

    core_trend = _multi_trend(core_vals)
    ocf_trend = _multi_trend(ocf_vals)
    rev_trend = _multi_trend(rev_vals)
    rev_yoy = yoy(revenue(latest), revenue(prev) if prev else None)
    core_yoy = yoy(profit.get("core_profit"), core_profit(prev).get("core_profit") if prev else None)
    ocf_yoy = yoy(operating_cash(latest), operating_cash(prev) if prev else None)
    op_yoy = yoy(
        classify_assets(latest).get("operating_assets"),
        classify_assets(prev).get("operating_assets") if prev else None,
    )
    inv_yoy = yoy(
        classify_assets(latest).get("investing_assets"),
        classify_assets(prev).get("investing_assets") if prev else None,
    )
    core_yoy = yoy(profit.get("core_profit"), core_profit(prev).get("core_profit") if prev else None)
    ocf_yoy = yoy(operating_cash(latest), operating_cash(prev) if prev else None)
    if op_yoy is None or inv_yoy is None:
        direction = "—"
    else:
        direction = "扩张" if op_yoy > 0 and inv_yoy > 0 else "收缩"
    if op_yoy is None or core_yoy is None or ocf_yoy is None:
        coherence, outlook_grade = "—", "—"
    elif op_yoy > 0 and core_yoy > 0 and ocf_yoy > 0:
        coherence, outlook_grade = "自洽", "优"
    else:
        coherence, outlook_grade = "待观察", "中"
    if direction == "—" and coherence == "—" and core_trend == "—" and ocf_trend == "—" and rev_trend == "—":
        outlook_evidence = "—"
    else:
        outlook_parts = [
            f"营业收入：近{len(rev_vals)}期{rev_trend}（最新同比 {fmt_pct(rev_yoy)}）",
            f"核心利润：近{len(core_vals)}期{core_trend}（最新同比 {fmt_pct(core_yoy)}）",
            f"经营现金流：近{len(ocf_vals)}期{ocf_trend}（最新同比 {fmt_pct(ocf_yoy)}）",
        ]
        if direction != "—":
            outlook_parts.append(f"扩张/收缩：{direction}")
        if coherence != "—":
            outlook_parts.append(f"是否自洽：{coherence}")
        outlook_evidence = "；".join(outlook_parts)

    rows: list[list[str]] = [
        [
            "战略方向（一看）",
            strategy.get("strategy_type", "—"),
            f"经营{fmt_pct(strategy.get('operating_asset_ratio'))} / 投资{fmt_pct(strategy.get('investing_asset_ratio'))}",
        ],
        [
            "竞争力（二看）",
            grade(comp.get("two_ends_index"), 1.2, 0.8),
            f"两头吃指数 {fmt_x(comp.get('two_ends_index'))}（上期 {fmt_x(prev_two_ends)}，{_trend(comp.get('two_ends_index'), prev_two_ends)})",
        ],
        [
            "效益质量（三看）",
            f"{fmt_yi(core_profit_val)}" if core_profit_val is not None else "—",
            f"核心利润 {fmt_yi(core_profit_val)}（上期 {fmt_yi(prev_core_profit_val)}，{_trend(core_profit_val, prev_core_profit_val)}）",
        ],
        [
            "价值创造（四看）",
            grade(profit.get("roe"), 15, 8),
            f"ROE {fmt_pct(profit.get('roe'))}（上期 {fmt_pct(prev_roe)}，{_trend(profit.get('roe'), prev_roe)}）",
        ],
        [
            "成本控制（五看）",
            grade(expense_ratio, 15, 25, higher_is_better=False),
            f"期间费用率合计 {fmt_pct(expense_ratio)}（上期 {fmt_pct(prev_expense)}，{_trend(expense_ratio, prev_expense, higher_is_better=False)}）",
        ],
        [
            "现金流质量（六看）",
            grade(cash.get("ocf_core_ratio"), 100, 80),
            f"OCF/核心利润 {fmt_pct(cash.get('ocf_core_ratio'))}（上期 {fmt_pct(prev_ocf_core)}，{_trend(cash.get('ocf_core_ratio'), prev_ocf_core)}）",
        ],
        [
            "风险状况（七看）",
            f"{risk_count}项" if risk_count else "无",
            hit_detail if hit_detail else "8 项均未触发",
        ],
        [
            "前景（八看）",
            outlook_grade,
            outlook_evidence,
        ],
    ]

    results = md_table(["方面", "评价", "关键证据"], rows)

    def _grade_score(g: str) -> int:
        return {"优": 90, "中": 65, "差": 30}.get(g, 60)

    score_weights = [0, 15, 15, 20, 10, 15, 15, 10]
    aspect_scores = [
        _grade_score(rows[1][1]),
        {"变好": 90, "持平": 70, "变差": 30}.get(_trend(core_profit_val, prev_core_profit_val), 60),
        _grade_score(rows[3][1]),
        _grade_score(rows[4][1]),
        _grade_score(rows[5][1]),
        100 if risk_count == 0 else (70 if risk_count <= 2 else 30),
        _grade_score(outlook_grade),
    ]
    score_total = round(sum(s * w for s, w in zip(aspect_scores, score_weights[1:])) / 100)
    conc: list[str] = []
    raw = ""
    formulas = [
        {
            "name": "战略方向（一看）",
            "formula": "投资占比>35%且投资增速>经营增速→投资主导；经营占比>65%→经营主导；否则混合",
            "meaning": "看公司的钱主要投在经营还是投资上，判断战略重心。",
            "reading": "无优劣之分，关键是战略与能力匹不匹配；投资主导型要盯投资回报，经营主导型要盯经营效率。",
        },
        {
            "name": "竞争力（二看）",
            "formula": "两头吃指数 ≥1.2 优，≥0.8 中，否则差",
            "meaning": "公司在产业链上的话语权，能否占用上下游资金。",
            "reading": "优说明两头吃、地位强；差说明被上下游占用资金，竞争力弱。",
        },
        {
            "name": "效益质量（三看）",
            "formula": "核心利润 = 营业收入 − 营业成本 − 税金及附加 − 销售/管理/研发/财务费用，以金额看趋势",
            "meaning": "主业自身赚了多少钱，只看核心利润金额，不看比率。",
            "reading": "金额越大越好；与上期比变好还是变差才是关键，持续下滑说明主业赚钱能力在减弱。",
        },
        {
            "name": "价值创造（四看）",
            "formula": "ROE ≥15% 优，≥8% 中，否则差",
            "meaning": "股东投入的回报率，是价值创造的核心标尺。",
            "reading": "优说明赚钱能力强；长期低于 8% 说明股东回报偏弱。",
        },
        {
            "name": "成本控制（五看）",
            "formula": "期间费用率合计（销售+管理+研发+财务）≤15% 优，≤25% 中，否则差",
            "meaning": "每 1 元收入要花多少期间费用，衡量费用管控水平。",
            "reading": "越低越好；偏高说明费用侵蚀利润，需看是哪一项费用在涨。",
        },
        {
            "name": "现金流质量（六看）",
            "formula": "OCF/核心利润 ≥100% 优，≥80% 中，否则差",
            "meaning": "主业利润有多少变成真金白银收回来。",
            "reading": "优说明利润足额变现；差说明利润是账面富贵。",
        },
        {
            "name": "风险状况（七看）",
            "formula": "8 项硬阈值逐项判定，触发即列出",
            "meaning": "商誉、存贷双高、负债率等 8 项硬阈值，触发哪项就列哪项，不做优中差评级。",
            "reading": "无触发最好；触发的每一项都要去七看核实具体数值和成因。",
        },
        {
            "name": "前景（八看）",
            "formula": "经营性资产、核心利润、经营现金流同比同向为正→自洽→优，否则中",
            "meaning": "投入、利润、现金三者是否同步向好，判断增长能不能持续。",
            "reading": "优说明扩张且自洽；中说明增长质量待观察，要看是哪一节掉了队。",
        },
        {
            "name": "综合评分",
            "formula": "竞争力15 + 效益质量15 + 价值创造20 + 成本控制10 + 现金流质量15 + 风险状况15 + 前景10 = 100（战略方向不计分）",
            "meaning": "七个方面按权重加权平均，满分 100 分。优90分、中65分、差30分、缺数据60分；效益质量按核心利润趋势变好90/持平70/变差30分；风险无触发100分、1~2项70分、3项及以上30分；战略方向本身无优劣，不参与评分。",
            "reading": "分数越高基本面越好，重点看丢分项是哪几个方面，再去对应的一看里找原因。分数只反映财报基本面，不构成买卖建议。",
        },
    ]
    return {
        "key": "summary",
        "no": 0,
        "name": "综合诊断",
        "raw": raw,
        "formulas": [_formula_dict(item) for item in formulas],
        "results": results,
        "table": results,
        "series": {"periods": [], "metrics": []},
        "dimensions": rows,
        "score_total": score_total,
        "score_weights": score_weights,
        "conclusions": conc,
        "text": _step(raw, formulas, results, conc),
    }


def build_views(series: list[dict[str, Any]], bundle: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """按一看~八看顺序构建全部视图。"""
    if bundle is None:
        from company.analysis.financialreport.metrics import compute_bundle

        bundle = compute_bundle(series)
    return [
        view_strategy(series),
        view_operating(series),
        view_profit(series),
        view_value(series),
        view_cost(series),
        view_quality(series),
        view_risk(series, bundle.get("flags") or []),
        view_outlook(series),
    ]



