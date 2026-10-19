"""Markdown 渲染：纯函数，输入 profile，输出 Markdown 文本。

本模块**不取数、不计算派生指标**——所有数字都来自 :mod:`company.analysis.businessoverview.bizprofile.engine`
组装好的 profile。这里只负责把结构化数据排版成章节。

渲染原则
--------
* **缺失即「—」**：任何 ``None`` 一律渲染为破折号，绝不按 0 处理（护栏 G4）；
* **每张表带报告期**：不同报告期的数据不混列（护栏 G5）；
* **口径如实披露**：命中的护栏逐条写进尾注；
* **不生成叙述性结论**：只做有数据支撑的机械陈述，不做主观判断。
"""

from __future__ import annotations

from typing import Any

from company.analysis.financialreport._common import fmt_num, fmt_pct, md_table

#: 维度键 → 章节小标题
DIM_TITLE: dict[str, str] = {
    "product": "按产品",
    "industry": "按行业",
    "area": "按地区",
}

#: 经营评述摘录的字数上限
REVIEW_EXCERPT_LIMIT = 1200


def _yi(value: Any) -> str:
    """金额 → 亿元字符串，缺失为「—」。"""
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number / 1e8:.2f}亿"


def _pct(value: Any, digits: int = 2) -> str:
    """0~1 小数 → 百分比字符串，缺失为「—」。"""
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def _pp(value: Any, digits: int = 2) -> str:
    """百分点变动，缺失为「—」。"""
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:+.{digits}f}pp"


def _text(value: Any) -> str:
    return str(value).strip() if value else ""


def _header(profile: dict[str, Any]) -> str:
    primary = profile.get("primary") or ""
    pack = (profile.get("dimensions") or {}).get(primary) or {}
    periods = profile.get("dim_periods") or {}
    latest = pack.get("report_date") or ""
    return (
        f"# {_text(profile.get('name')) or profile.get('code')}（{profile.get('code')}）主营业务构成\n\n"
        f"> 数据截止：{latest} | 生成日期：{profile.get('cutoff_date', '')} | "
        f"数据源：{profile.get('source_label', '')}\n"
        f"> 主维度：{DIM_TITLE.get(primary, '')} | "
        f"各维度可得期数：{'、'.join(f'{DIM_TITLE.get(k, k)} {v}' for k, v in sorted(periods.items())) or '—'} | "
        f"页面：{profile.get('page', '')}\n"
    )


def _overview(profile: dict[str, Any]) -> str:
    primary = profile.get("primary") or ""
    pack = (profile.get("dimensions") or {}).get(primary) or {}
    gloss = profile.get("gloss") or (lambda t: t)

    main_business = _text(pack.get("main_business"))
    product_type = _text(pack.get("product_type"))
    product_names = pack.get("product_name_list") or []
    scope = _text(pack.get("scope"))

    lines = ["## 一、公司与主营业务速览", ""]
    if main_business:
        lines.append(f"**主营业务**：{main_business}")
        lines.append("")
    if product_type:
        lines.append(f"**产品类型**：{product_type}")
        lines.append("")
    if product_names:
        lines.append(f"**主要产品**：{'、'.join(str(n) for n in product_names)}")
        lines.append("")
    if scope:
        lines.append(f"**经营范围**：{scope}")
        lines.append("")
    if not any((main_business, product_type, product_names, scope)):
        lines.append("（主营介绍与经营范围未在同花顺 F10 页面披露）")
        lines.append("")

    # 白话版（词典替换，仅措辞替换，不改数字）
    plain = gloss(main_business)
    if plain and plain != main_business:
        lines.append(f"**白话理解**：{plain}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _concentration_table(profile: dict[str, Any]) -> str:
    dimensions = profile.get("dimensions") or {}
    headers = ["维度", "最新报告期", "一级分部数", "主营合计（亿元）", "收入占比合计", "整体毛利率", "CR3", "HHI"]
    rows: list[list[str]] = []
    for key, pack in dimensions.items():
        segments = pack.get("_latest_segments") or []
        totals = pack.get("totals") or {}
        income = (totals.get("income") or {}).get("total")
        conc = pack.get("_concentration") or {}
        rows.append([
            DIM_TITLE.get(key, key),
            pack.get("report_date") or "—",
            str(len(segments)),
            _yi(income),
            _pct(pack.get("total_ratio")),
            _pct(pack.get("_overall_margin")),
            _pct(conc.get("cr3")),
            fmt_num(conc.get("hhi"), 4) if conc.get("hhi") is not None else "—",
        ])
    return md_table(headers, rows)


def _overview_section(profile: dict[str, Any]) -> str:
    lines = ["## 二、主营构成总览", "", _concentration_table(profile), ""]
    lines.append("> 整体毛利率由「Σ分部毛利 ÷ Σ分部收入」派生；CR3/HHI 按一级分部的收入占比计算。")
    lines.append("")
    lines.append("> 三个维度由公司分别披露，期数与口径不同，不可横向当作同一口径比较。")
    return "\n".join(lines)


def _dimension_table(pack: dict[str, Any]) -> str:
    segments = pack.get("_latest_segments") or []
    headers = ["分部", "营业收入（亿元）", "收入占比", "收入同比", "毛利率", "毛利占比"]
    rows: list[list[str]] = []
    for s in segments:
        rows.append([
            _text(s.get("item_name")) or "—",
            _yi(s.get("revenue")),
            _pct(s.get("revenue_ratio")),
            _pct(s.get("revenue_yoy")),
            _pct(s.get("gross_margin")),
            _pct(s.get("gross_profit_ratio")),
        ])
    return md_table(headers, rows)


def _dimensions_section(profile: dict[str, Any]) -> str:
    dimensions = profile.get("dimensions") or {}
    lines = ["## 三、分维度构成明细", ""]
    for index, (key, pack) in enumerate(dimensions.items(), 1):
        report_date = pack.get("report_date") or "—"
        lines.append(f"### 3.{index} {DIM_TITLE.get(key, key)}（{report_date}）")
        lines.append("")
        lines.append(_dimension_table(pack))
        lines.append("")
        total_ratio = pack.get("total_ratio")
        if total_ratio is not None:
            lines.append(f"> 注：收入占比合计 {_pct(total_ratio)}；毛利率列为该分部自身毛利率，"
                         "毛利占比为该分部毛利占全部分部毛利之比。")
            lines.append("")
    return "\n".join(lines).rstrip()


def _migration_section(profile: dict[str, Any]) -> str:
    primary = profile.get("primary") or ""
    pack = (profile.get("dimensions") or {}).get(primary) or {}
    rows_data = pack.get("_migration") or []
    periods = pack.get("periods") or []
    cur_date = periods[0].get("report_date") if periods else ""
    prev_date = periods[1].get("report_date") if len(periods) >= 2 else ""

    lines = ["## 四、收入结构与变化", ""]
    if not rows_data:
        lines.append("（缺少可对比的上期数据）")
        return "\n".join(lines)

    lines.append(f"### 4.1 占比迁移（{cur_date} vs {prev_date}）")
    lines.append("")
    headers = ["分部", f"{prev_date} 占比", f"{cur_date} 占比", "变动", "匹配状态"]
    rows: list[list[str]] = []
    for row in rows_data:
        rows.append([
            _text(row.get("item_name")) or "—",
            _pct(row.get("prev_ratio")),
            _pct(row.get("cur_ratio")),
            _pp(row.get("delta_pp")),
            _text(row.get("status")) or "—",
        ])
    lines.append(md_table(headers, rows))
    lines.append("")

    lines.append("### 4.2 合计收入与同比")
    lines.append("")
    totals = pack.get("totals") or {}
    income = totals.get("income") or {}
    cost = totals.get("cost") or {}
    gross_profit = totals.get("gross_profit") or {}
    headers2 = ["项目", "金额（亿元）", "同比"]
    rows2 = [
        ["主营业务收入", _yi(income.get("total")), _pct(income.get("yoy"))],
        ["营业成本", _yi(cost.get("total")), _pct(cost.get("yoy"))],
        ["毛利", _yi(gross_profit.get("total")), _pct(gross_profit.get("yoy"))],
    ]
    lines.append(md_table(headers2, rows2))
    lines.append("")
    lines.append("> 合计口径取自同花顺 F10「主营构成」合计行；同比为该合计行披露值。")
    return "\n".join(lines)


def _profitability_section(profile: dict[str, Any]) -> str:
    primary = profile.get("primary") or ""
    pack = (profile.get("dimensions") or {}).get(primary) or {}
    segments = pack.get("_latest_segments") or []
    report_date = pack.get("report_date") or "—"

    lines = ["## 五、盈利结构", ""]
    lines.append(f"### 5.1 分部盈利贡献（{report_date}）")
    lines.append("")
    headers = ["分部", "毛利率", "毛利额（亿元）", "毛利占比", "收入占比", "收入-毛利贡献差"]
    rows: list[list[str]] = []
    negatives: list[str] = []
    for s in segments:
        margin = s.get("gross_margin")
        if margin is not None and float(margin) < 0:
            negatives.append(_text(s.get("item_name")))
        rev_ratio = s.get("revenue_ratio")
        gp_ratio = s.get("gross_profit_ratio")
        diff = None
        if rev_ratio is not None and gp_ratio is not None:
            diff = (float(gp_ratio) - float(rev_ratio)) * 100
        rows.append([
            _text(s.get("item_name")) or "—",
            _pct(margin),
            _yi(s.get("gross_profit")),
            _pct(gp_ratio),
            _pct(rev_ratio),
            _pp(diff),
        ])
    lines.append(md_table(headers, rows))
    lines.append("")
    lines.append(f"- 整体毛利率（派生）：{_pct(pack.get('_overall_margin'))}")
    lines.append(f"- 负毛利分部：{'、'.join(negatives) if negatives else '无'}")
    lines.append("")
    lines.append("> 「收入-毛利贡献差」为该分部毛利占比减收入占比（百分点），"
                 "为正表示该分部对利润的贡献高于对收入的贡献。")
    return "\n".join(lines)


def _review_section(profile: dict[str, Any]) -> str:
    picked = profile.get("review_picked") or {}
    lines = ["## 六、经营评述摘录", ""]
    if not picked:
        lines.append("（同花顺 F10 未披露董事会经营评述，或页面结构已变更）")
        return "\n".join(lines)

    length = int(picked.get("length") or 0)
    lines.append(
        f"> 报告期 {picked.get('report_date') or '—'} | {length} 字 | "
        f"来源：同花顺 F10 经营分析"
    )
    lines.append("")

    text = _text(picked.get("review"))
    if len(text) > REVIEW_EXCERPT_LIMIT:
        excerpt = text[:REVIEW_EXCERPT_LIMIT].rstrip() + "……（已截断，完整内容见同花顺 F10 页面）"
    else:
        excerpt = text
    lines.append(excerpt)
    lines.append("")
    lines.append("> 本节为原文节选，未做改写或摘要。")
    return "\n".join(lines)


def _classification_section(profile: dict[str, Any]) -> str:
    classification = profile.get("classification") or {}
    lines = ["## 七、业务归类与白话解读", ""]
    if not classification.get("available"):
        lines.append("（业务词典未启用）")
        return "\n".join(lines)

    if classification.get("generic"):
        lines.append("- 业务大类：未分类（词典未命中）")
        lines.append("- 命中情况：所有分部名称均未命中业务词典")
    else:
        lines.append(f"- 业务大类：{classification.get('main_category') or '—'}")
        model = classification.get("main_model") or ""
        hint = classification.get("model_hint") or ""
        lines.append(f"- 赚钱模式：{model}{f'（{hint}）' if hint else ''}")
        lines.append(f"- 典型客群：{classification.get('main_buyers') or '—'}")

    hits = classification.get("hits") or []
    if hits:
        lines.append("")
        lines.append("| 分部 | 命中关键词 | 业务大类 | 赚钱模式 | 典型客群 |")
        lines.append("|---|---|---|---|---|")
        for hit in hits:
            lines.append(
                f"| {_text(hit.get('item_name'))} | {_text(hit.get('keyword'))} | "
                f"{_text(hit.get('category'))} | {_text(hit.get('model'))} | "
                f"{_text(hit.get('buyers'))} |"
            )

    unmatched = classification.get("unmatched") or []
    if unmatched:
        lines.append("")
        lines.append(f"> 词典未命中：{'、'.join(str(x) for x in unmatched)}"
                     "（未命中不代表无业务属性，仅表示静态词典未收录）")
    lines.append("")
    lines.append("> 本节由静态业务词典（关键词字符串匹配）派生，规则确定、可复现，"
                 "不含任何模型推断。")
    return "\n".join(lines)


def _footnote(profile: dict[str, Any]) -> str:
    dimensions = profile.get("dimensions") or {}
    primary = profile.get("primary") or ""
    pack = (dimensions.get(primary) or {})
    hits = profile.get("guardrails") or []

    lines = ["## 尾注：数据来源与局限", ""]
    lines.append(
        f"- 主营数据：同花顺 F10 经营分析（页面 {profile.get('page', '')}），"
        f"主维度「{DIM_TITLE.get(primary, '')}」最新报告期 {pack.get('report_date') or '—'}。"
    )
    lines.append(
        "- 本报告由确定性规则渲染，**未调用任何模型**；"
        "所有数字直接取自上述来源，或由其派生（派生方式已在各章节注明）。"
    )
    if hits:
        lines.append("")
        lines.append("口径提示：")
        lines.append("")
        for hit in hits:
            lines.append(f"- **[{hit.get('id')}]** {hit.get('title')}：{hit.get('detail')}")
    else:
        lines.append("")
        lines.append("- 本次取数未触发口径告警。")
    return "\n".join(lines)


def render_markdown(profile: dict[str, Any]) -> str:
    """渲染完整报告（纯函数）。"""
    sections = [
        _header(profile),
        _overview(profile),
        _overview_section(profile),
        _dimensions_section(profile),
        _migration_section(profile),
        _profitability_section(profile),
        _review_section(profile),
        _classification_section(profile),
        _footnote(profile),
    ]
    return "\n\n".join(s.strip() for s in sections if s and s.strip()) + "\n"


__all__ = ["DIM_TITLE", "REVIEW_EXCERPT_LIMIT", "render_markdown"]
