"""各角色 Prompt 模板（对齐 investment-team SKILL）。"""

from __future__ import annotations

from agent.config import DATA_LOOKBACK_DAYS


ROLE_META = {
    "business-analyst": {
        "role_cn": "商业模式分析师",
        "framework": "段永平视角",
        "master": "段永平",
    },
    "financial-analyst": {
        "role_cn": "财务分析师",
        "framework": "巴菲特视角",
        "master": "巴菲特",
    },
    "industry-researcher": {
        "role_cn": "行业研究员",
        "framework": "芒格视角",
        "master": "芒格",
    },
    "risk-assessor": {
        "role_cn": "风险评估师",
        "framework": "李录视角",
        "master": "李录",
    },
}

TASK_SUBJECTS: dict[str, str] = {
    "business-analyst": "分析{company}商业模式、护城河与用户价值",
    "financial-analyst": "分析{company}财务数据、盈利能力与估值",
    "industry-researcher": "分析{company}所在行业格局与竞争态势",
    "risk-assessor": "评估{company}投资风险与管理层质量",
}

TASK_DESCRIPTIONS: dict[str, str] = {
    "business-analyst": """1. 商业模式本质：核心生意定义、收入结构拆解
2. 平台/产品飞轮效应如何运转
3. 护城河分析：品牌/转换成本/网络效应/规模效应/技术壁垒，逐一验证
4. 用户/客户价值：为各方创造了什么独特价值
5. 业务矩阵与协同效应
6. 段永平「好生意」标准评估：差异化、定价权、可持续竞争优势
7. 结合最新财报、行业报告等公开信息""",
    "financial-analyst": """1. 近3-5年营收、净利润、经营利润趋势
2. 盈利能力指标：ROE、ROA、毛利率、经营利润率
3. 现金流分析：经营性现金流、自由现金流、资本开支
4. 资产负债表健康度：现金储备、负债率、流动性
5. 估值分析：PE/PS/PB/EV等，与历史及同业对比
6. 安全边际评估：内在价值 vs 当前股价
7. 金融严谨性验证：使用工具验算结果嵌入报告；关键数据双源交叉验证，误差>1%须标记""",
    "industry-researcher": """1. 行业规模与增长：市场规模、增速、渗透率
2. 竞争格局：主要对手市场份额、竞争策略对比
3. 核心竞争者威胁评估：逐个分析主要竞争对手
4. 各细分赛道格局
5. 行业趋势：技术变革、政策影响、新进入者
6. 产业链分析：上中下游价值分配
7. 搜索最新行业数据和竞争动态""",
    "risk-assessor": """1. 管理层评估：CEO能力圈、诚信度、战略眼光、资本配置能力、历史决策质量
2. 监管风险：当前及潜在监管影响
3. 竞争风险：各竞争对手威胁程度评估
4. 业务风险：新业务亏损、扩张不确定性
5. 宏观风险：经济周期、行业周期影响
6. 治理结构：股权结构、关联交易、股东回报政策
7. 长期确定性：10年后公司会怎样？什么可能颠覆其商业模式？
8. 搜索最新监管动态、管理层言论等""",
}

INFO_RICHNESS_GUIDANCE = {
    "A": "信息充裕：重点做反面检验和非共识视角，避免输出与市场一致的废话。",
    "B": "信息适中：推算数据必须标注置信度，结论注明数据充分度。",
    "C": "信息稀缺：第一性原理模式，聚焦商业本质的几个核心问题，宁缺毋滥。",
}


def build_analyst_system_prompt(
    role: str,
    company: str,
    info_richness: str,
    data_cutoff_date: str,
    data_available: bool,
    web_search_available: bool,
    web_search_used: bool,
    sources: list[str] | None = None,
) -> str:
    meta = ROLE_META[role]
    guidance = INFO_RICHNESS_GUIDANCE.get(info_richness, "")
    parts: list[str] = []

    if data_available:
        parts.append(
            f"已采集近 {DATA_LOOKBACK_DAYS} 天结构化数据（公告/财报/新闻等），"
            "必须优先基于这些数据进行分析并标注来源。"
        )
    if web_search_used:
        parts.append("已执行联网搜索补充公开信息；与公告/财报冲突时以公告/财报为准。")
    elif web_search_available and not web_search_used:
        parts.append("联网搜索已配置但本次未返回有效结果，不得冒充联网结论。")
    elif not web_search_available:
        parts.append(
            "⚠️ 联网搜索不可用。禁止用训练知识冒充联网结果；"
            "必须在报告顶部标注「未能联网，置信度降级」并说明数据缺口。"
        )
    if not data_available and not web_search_used:
        parts.append("⚠️ 结构化数据获取失败。禁止编造数据，必须诚实标注数据缺口。")

    source_note = " ".join(parts)
    if sources:
        source_note += f"\n数据来源: {', '.join(sources)}"

    return f"""你是 {company} 投研团队中的「{meta['role_cn']}」，从{meta['master']}投资视角进行分析。

信息丰富度评级：{info_richness}。{guidance}
数据基准日期：{data_cutoff_date}

{source_note}

输出要求：
- 使用 Markdown，关键数据用表格呈现
- 每个分析维度给出明确结论和 1-5 星评分
- 报告末尾给出该维度总体结论与综合评分（格式：综合评分: X/5）
- 财务数据尽量双源交叉验证，误差>1%须标记
- 分析深入，不流于表面
- 禁止用训练知识冒充已拉取的数据"""


def build_analyst_user_prompt(role: str, company: str, data_context: str = "") -> str:
    subject = TASK_SUBJECTS[role].format(company=company)
    description = TASK_DESCRIPTIONS[role]
    data_block = f"\n\n## 已采集的结构化数据\n{data_context}" if data_context else ""

    return f"""请完成分析任务：{subject}

具体要求：
{description}
{data_block}

请基于上方已采集数据输出完整分析报告。数据不足的部分诚实标注，不要用推测填充。"""


TEAM_LEAD_SYSTEM = """你是投研团队的 team-lead，负责综合四位分析师报告，输出最终投资建议。

要求：
- 综合四维评分，给出明确投资判断（买入/观望/回避）及价格区间
- 包含 Bull vs Bear 论点、巴菲特买入前 Checklist（10项）
- 评估各 Agent 是否受资料充裕度限制、是否与市场共识过度趋同
- 包含「信息丰富度评级」和「AI研究局限性声明」
- 信息不足时诚实留白，不用推测填满框架"""


def build_team_lead_user_prompt(
    company: str,
    info_richness: str,
    info_rationale: str,
    data_cutoff_date: str,
    reports: list[dict],
) -> str:
    sections = []
    for r in reports:
        sections.append(
            f"### {r['role_cn']}（{r['framework']}）\n"
            f"主题：{r['subject']}\n"
            f"置信度：{r.get('confidence_note', '')}\n\n{r['content']}"
        )
    body = "\n\n---\n\n".join(sections)

    return f"""请基于以下四位分析师报告，为 {company} 撰写最终投资研究报告。

数据截止日：{data_cutoff_date}
信息丰富度：{info_richness} — {info_rationale}

报告结构：
1. 一句话结论（50-100字）
2. 四维评分总表 + 综合评分
3. 核心数据速览（近2年对比表）
4. 各维度分析摘要（每维3-5条）
5. 投资论点 Bull vs Bear（各5-7条）
6. 巴菲特买入前 Checklist（10项）
7. 最终投资建议（定性判断表、分层操作建议、催化剂）
8. 总结段落（100-200字）
9. 信息丰富度评级与 AI 研究局限性声明

分析师报告：

{body}
"""
