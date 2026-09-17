"""张新民「八看」财报解读 Prompt 模板。"""

from __future__ import annotations

ANALYST_SYSTEM = """你是财务报表分析专家，严格遵循张新民教授「八看」分析框架。

硬性规则：
1. 每个结论必须引用预计算指标或表格中的具体数字，禁止编造
2. 使用框架术语：核心利润、经营性资产、投资性资产、经营性负债、金融性负债、两头吃、三脱节
3. 利润表/现金流量表为报告期累计数（中报=上半年，三季报=前三季度），必须说明口径。分析对象是最新定期报告（年报/半年报/季报都要用），禁止默认当成最近年报；同比只用同口径（中报对中报、三季报对三季报）
4. 数据未披露时写「数据未披露」，禁止推测。预计算表中已有数字的指标（含二次加工指标）一律视为已披露，必须引用表中数字，禁止写未披露
5. 不做买卖建议，只做财务状况质量诊断
6. 章节标题、原始数据表、解读/小结标题由系统固定拼装。你只填写条目正文，禁止输出任何 Markdown 标题（# / ## / ###）
7. 按用户给出的编号逐条填写，不要增删条目、不要另起章节名
8. 关键数字用 **加粗**；最后单独一段，必须以「本章小结：」开头，2-3 句
9. 表下「计算公式」给出二次加工口径，解读时须点明公式含义，不得把加工指标当成原始披露科目"""

OUTPUT_CONTRACT = """输出要求（必须遵守）：
- 禁止输出 Markdown 标题（不要写 #、##、###）
- 禁止重复章节名，禁止写「解读」「原始数据」作为小标题
- 按下面编号 1. 2. 3. … 逐条填写，不要增删条目
- 每条必须引用表中具体数字；缺数据写「数据未披露」，禁止空章。表中已有该列数字即视为已披露
- 二次加工指标须按表下「计算公式」解释口径
- 最后单独一段，以「本章小结：」开头，2-3 句"""


def _base_context(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    strategy_type: str,
    zhang_summary: str,
    flags: list[str],
) -> str:
    flag_text = "\n".join(f"- {f}" for f in flags) if flags else "- 暂无重大警示"
    return f"""公司：{stock_name}（{stock_code})
分析基准日：{data_cutoff_date}
战略类型（规则引擎判定）：{strategy_type}

## 规则引擎预计算摘要
{zhang_summary}

## 风险警示
{flag_text}
"""


def build_strategy_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    strategy_type: str,
    zhang_summary: str,
    flags: list[str],
    table: str,
    data_context: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, strategy_type, zhang_summary, flags)}

## 一看：战略——资产配置表（Python 预计算）
{table}

## 补充上下文
{data_context[:6000]}

请从「一看：战略」填写以下条目：
1. 企业属于经营主导型、投资主导型还是混合型？资源配置揭示什么战略意图？
2. 经营性资产 vs 投资性资产的结构变化趋势
3. 是否存在控制性投资扩张（长期股权投资、商誉增加）
4. 重资产还是轻资产？固定资产占比是否合理？

{OUTPUT_CONTRACT}
"""


def build_operating_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    strategy_type: str,
    zhang_summary: str,
    flags: list[str],
    table: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, strategy_type, zhang_summary, flags)}

## 二看：经营资产管理与竞争力表（Python 预计算）
{table}

请从「二看：经营资产管理与竞争力」填写以下条目：
1. 两头吃指数反映的上下游议价能力（>1 为强势）。这是二次加工指标，须按表下公式解释：(应付账款+预收/合同负债)÷(应收账款+预付款项)
2. 存货周转天数、应收周转天数的变化及含义（均为二次加工，公式见表下）
3. 固定资产周转效率
4. 两金（应收+存货）是否存在积压风险

{OUTPUT_CONTRACT}
"""


def build_profit_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    strategy_type: str,
    zhang_summary: str,
    flags: list[str],
    table: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, strategy_type, zhang_summary, flags)}

## 三看：效益与质量表（Python 预计算）
{table}

请从「三看：效益与质量」填写以下条目：
1. 核心利润规模与核心利润率（张新民定义：营收-成本-税金-四项费用）
2. 扣非净利润与归母净利润的差距，利润成色
3. 营收增速 vs 核心利润增速的匹配度
4. 毛利率趋势（表中已给出毛利率列，必须引用具体数字；仅当该列为「—」时才写数据未披露）

{OUTPUT_CONTRACT}
"""


def build_value_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    strategy_type: str,
    zhang_summary: str,
    flags: list[str],
    table: str,
    peer_context: str = "",
) -> str:
    peer_block = peer_context.strip() or "（未采集到同业估值对照。行业对比一律写「数据未披露」，禁止用训练知识补数。）"
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, strategy_type, zhang_summary, flags)}

## 四看：价值创造表（Python 预计算）
{table}

## 同业/估值对照（如有）
{peer_block}

请从「四看：价值创造」填写以下条目（本章必须写满，禁止空白）：
1. ROE、ROA、ROIC 水平及近年趋势
2. 高回报来自净利率、资产周转还是权益乘数（杜邦分解；缺列写「数据未披露」）
3. 利润积累对净资产增长的贡献（归母净利润 vs 净资产变化）
4. 与行业/同业对比的价值创造能力；无对照数据则写「数据未披露」

{OUTPUT_CONTRACT}
"""


def build_cost_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    strategy_type: str,
    zhang_summary: str,
    flags: list[str],
    table: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, strategy_type, zhang_summary, flags)}

## 五看：成本决定机制表（Python 预计算）
{table}

请从「五看：成本决定机制」填写以下条目：
1. 营业成本率、各项费用率的变化——成本由决策/管理/核算哪层驱动？
2. 研发费用率反映的技术投入
3. 财务费用率变化对利润的侵蚀
4. 毛利率与费用率的联动

{OUTPUT_CONTRACT}
"""


def build_quality_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    strategy_type: str,
    zhang_summary: str,
    flags: list[str],
    asset_table: str,
    liab_table: str,
    cash_table: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, strategy_type, zhang_summary, flags)}

## 六看：财务状况质量

### 资产结构
{asset_table}

### 负债结构
{liab_table}

### 现金流质量
{cash_table}

请从「六看：财务状况质量」填写以下条目：
1. 货币资金、应收、存货、商誉、长期投资各自的质量
2. 经营性负债 vs 金融性负债的资本结构质量
3. 经营现金流对核心利润的验证（利润含金量试金石）
4. 是否存在存贷双高、商誉过高等异常

{OUTPUT_CONTRACT}
"""


def build_risk_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    strategy_type: str,
    zhang_summary: str,
    flags: list[str],
) -> str:
    flag_text = "\n".join(f"- {f}" for f in flags) if flags else "- 暂无"
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, strategy_type, zhang_summary, flags)}

## 七看：风险——规则引擎警示清单
{flag_text}

请从「七看：风险」填写以下条目：
1. 经营风险（市场、产品、客户集中度）
2. 财务风险（偿债、现金流断裂、过度融资）
3. 利润结构风险（非主业利润依赖）
4. 三脱节风险（应收/存货/现金流与利润不匹配）
5. 对每个警示给出严重程度和应对观察点

{OUTPUT_CONTRACT}
"""


def build_outlook_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    strategy_type: str,
    zhang_summary: str,
    flags: list[str],
    data_context: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, strategy_type, zhang_summary, flags)}

## 八看：前景——补充上下文
{data_context[:4000]}

请从「八看：前景」填写以下条目：
1. 从资产结构变化判断扩张还是收缩
2. 经营性资产、核心利润、经营现金流是否同步改善
3. 行业天花板与增长可持续性
4. 未来 1-3 年需重点跟踪的财务指标

{OUTPUT_CONTRACT}
"""


def build_synthesis_prompt(
    stock_name: str,
    stock_code: str,
    strategy_type: str,
    diagnosis_table: str,
    section_strategy: str,
    section_operating: str,
    section_profit: str,
    section_value: str,
    section_cost: str,
    section_quality: str,
    section_risk: str,
    section_outlook: str,
) -> str:
    return f"""公司：{stock_name}（{stock_code}）
战略类型：{strategy_type}

## 综合诊断表（Python 预计算）
{diagnosis_table}

## 各章摘要
### 一看
{section_strategy[:1500]}

### 二看
{section_operating[:1000]}

### 三看
{section_profit[:1000]}

### 四看
{section_value[:800]}

### 五看
{section_cost[:800]}

### 六看
{section_quality[:1000]}

### 七看
{section_risk[:800]}

### 八看
{section_outlook[:1000]}

请按下列条目填写「综合诊断」（禁止输出 Markdown 标题，禁止重复「综合诊断」章名）：
1. Executive Summary（200字以内）：战略定性、利润质量、最大风险、最大亮点
2. 战略-质量-现金流是否自洽？
3. 五个维度评价（战略一致性、利润含金量、资产质量、偿债安全、增长可持续性），用简洁分点，不要再套一层大标题
4. 后续跟踪建议（3-5个关键指标）

{OUTPUT_CONTRACT}
"""


def build_assemble_header(
    stock_name: str,
    stock_code: str,
    industry: dict,
    data_cutoff_date: str,
    strategy_type: str,
    latest_period: str = "",
    period_kind: str = "",
    coverage: str = "",
) -> str:
    industry_name = industry.get("name") or industry.get("l3_name") or ""
    ind_part = f" | 行业：{industry_name}" if industry_name else ""
    period_part = ""
    if latest_period:
        kind = f"（{period_kind}）" if period_kind else ""
        period_part = f" | 最新定期报告：{latest_period}{kind}"
    coverage_line = f"\n> 数据覆盖：{coverage}" if coverage else ""
    return f"""# {stock_name}（{stock_code}）张新民「八看」财报解读

> 分析基准日：{data_cutoff_date} | 战略类型：{strategy_type}{ind_part}{period_part}
> 框架：张新民「八看」 | 数据来源：东财 F10 · 申万行业 · 规则引擎预计算
> 说明：覆盖年报、半年报、一季报、三季报。利润表/现金流量表为报告期累计数，非单季度；同比用同口径。{coverage_line}
"""
