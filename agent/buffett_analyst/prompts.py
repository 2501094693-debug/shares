"""巴菲特读表 Prompt 模板。"""

from __future__ import annotations

ANALYST_SYSTEM = """你是财务报表分析专家，严格按沃伦·巴菲特的读表方法解读。只还原经济真实，不写卖方研报腔。

硬性规则：
1. 每个结论必须引用预计算指标或表格中的具体数字，禁止编造、禁止心算所有者盈余
2. 只用巴菲特术语：所有者盈余、维持性资本开支、经济商誉、受限盈利、能力圈、安全边际
3. 禁止使用张新民框架术语：核心利润、两头吃、三脱节
4. 利润表/现金流量表为报告期累计数（中报=上半年，三季报=前三季度），必须说明口径
5. 数据未披露时写「数据未披露」，禁止推测。预计算表中已有数字的指标一律视为已披露，必须引用
6. 规则引擎给出的生意类型（伟大/优秀/平庸/糟糕/数据不足）禁止改写，只能解释依据
7. 章节标题、原始数据表、解读/小结标题由系统固定拼装。你只填写条目正文，禁止输出任何 Markdown 标题（# / ## / ###）
8. 按用户给出的编号逐条填写，不要增删条目、不要另起章节名
9. 关键数字用 **加粗**；最后单独一段，必须以「本章小结：」开头，2-3 句
10. 表下「计算公式」给出二次加工口径，解读时须点明公式含义"""

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
    business_type: str,
    buffett_summary: str,
    flags: list[str],
) -> str:
    flag_text = "\n".join(f"- {f}" for f in flags) if flags else "- 暂无重大警示"
    return f"""公司：{stock_name}（{stock_code}）
分析基准日：{data_cutoff_date}
生意类型（规则引擎判定，禁止改写）：{business_type}

## 规则引擎预计算摘要
{buffett_summary}

## 风险警示
{flag_text}
"""


def build_understand_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    business_type: str,
    buffett_summary: str,
    flags: list[str],
    data_context: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, business_type, buffett_summary, flags)}

## 补充上下文（公司画像、分部收入）
{data_context[:6000]}

请从「一、生意能否看懂」填写以下条目：
1. 用一句话说清这家公司靠什么赚钱
2. 收入主要来自哪些产品/地区（必须引用分部或画像中的数字；没有则写数据未披露）
3. 十年后大概率是否还在做这件事？哪些变量会让你看不懂
4. 这门生意是否落在能力圈内？给出「能看懂 / 部分看懂 / 看不懂」，看不懂时必须写明综合判决不得给出「进一步研究」的乐观结论

{OUTPUT_CONTRACT}
"""


def build_owner_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    business_type: str,
    buffett_summary: str,
    flags: list[str],
    table: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, business_type, buffett_summary, flags)}

## 二、所有者盈余表（Python 预计算）
{table}

请从「二、所有者盈余」填写以下条目：
1. 引用上沿、下沿和 OCF−资本开支三列，说明报告盈利与能取出的现金差在哪里
2. 资本开支更像维持还是扩张（结合 capex 与折旧；增长期 capex 高不等于差生意）
3. 若表中出现「未披露」，点名折旧摊销附注缺失导致下沿失效
4. 利润含金量：经营现金流是否覆盖净利润（引用 OCF/净利润或表中经营现金流与 (a)）

{OUTPUT_CONTRACT}
"""


def build_capital_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    business_type: str,
    buffett_summary: str,
    flags: list[str],
    table: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, business_type, buffett_summary, flags)}

## 三、资本饥饿表（Python 预计算）
{table}

请从「三、资本饥饿与四种生意」填写以下条目：
1. 解释规则引擎给出的生意类型「{business_type}」为什么成立（引用有形ROE、capex/D&A、增量资本回报），禁止改写类型
2. 这门生意饿不饿资本：PPE/营收、capex/D&A 说明什么
3. 增量资本回报或「负增量资本仍增利」意味着所有者在变富还是在摊薄
4. 仅当固定资产很重且毛利率偏低时，才讨论受限盈利/通胀伤害；否则明确写不适用

{OUTPUT_CONTRACT}
"""


def build_honesty_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    business_type: str,
    buffett_summary: str,
    flags: list[str],
    table: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, business_type, buffett_summary, flags)}

## 四、会计与资本配置表（Python 预计算）
{table}

请从「四、会计诚实与资本配置」填写以下条目：
1. 商誉规模：会计商誉是否在膨胀？有无把购买法溢价误当成费用消失
2. 扣非占比与非经常项目：报告盈利的记分卡有没有被摆弄
3. 多余现金怎么用：分红、吸收投资/发股、借款与还债（引用表中数字）
4. 留存 1 美元测试的近似结果：累计利润、Δ净资产、是否发股稀释

{OUTPUT_CONTRACT}
"""


def build_synthesis_prompt(
    stock_name: str,
    stock_code: str,
    business_type: str,
    diagnosis_table: str,
    understand_verdict: str,
    section_understand: str,
    section_owner: str,
    section_capital: str,
    section_honesty: str,
    valuation_context: str,
) -> str:
    return f"""公司：{stock_name}（{stock_code}）
生意类型（禁止改写）：{business_type}
一章对能力圈的判断摘录：{understand_verdict}

## 综合诊断表（Python 预计算）
{diagnosis_table}

## 估值与同业（只可引用此块数字，禁止自造目标价）
{valuation_context.strip() or "（未采集到估值对照。安全边际一律写「数据未披露」，禁止用训练知识补数。）"}

## 各章摘要
### 一、生意能否看懂
{section_understand[:1500]}

### 二、所有者盈余
{section_owner[:1200]}

### 三、资本饥饿
{section_capital[:1200]}

### 四、会计与资本配置
{section_honesty[:1200]}

请按下列条目填写「五、综合判决」（禁止输出 Markdown 标题）：
1. 六问逐条回答，每问必须引用前文或表中数字：能否理解；利润是不是现金；所有者盈余上沿/下沿；增量资本回报；记分卡是否被改；多余现金用途
2. 若第一章判定为「看不懂」，本条必须写：不得给出「值得进一步研究」，态度只能是观望或回避，并说明原因
3. 安全边际：只引用估值与同业表中的 PE/PB/FCF 等已有数字，判断够不够；禁止新做三情景模型或给出精确内在价值点估计
4. 综合态度必须三选一：值得进一步研究 / 观望 / 回避，并给出一句话理由（不超过 80 字）

{OUTPUT_CONTRACT}
"""


def build_assemble_header(
    stock_name: str,
    stock_code: str,
    industry: dict,
    data_cutoff_date: str,
    business_type: str,
) -> str:
    industry_name = industry.get("name") or industry.get("l3_name") or ""
    ind_part = f" | 行业：{industry_name}" if industry_name else ""
    return f"""# {stock_name}（{stock_code}）巴菲特读表

> 分析基准日：{data_cutoff_date} | 生意类型：{business_type}{ind_part}
> 框架：所有者盈余（1986）· 有形回报 · 资本配置 | 数据来源：东财 F10 · 申万行业 · 规则引擎预计算
> 说明：利润表/现金流量表为报告期累计数，非单季度。所有者盈余下沿在折旧摊销未披露时标为未披露。
"""
