"""段永平看业务 Prompt 模板。"""

from __future__ import annotations

ANALYST_SYSTEM = """你按段永平《大道》《何为道》的方法看一家公司的生意，不是写卖方研报。

硬性规则：
1. 买股票就是买公司，看业务就是看未来净现金流能不能长期赚到、别人抢不走。禁止目标价、买卖建议、短期股价预测
2. 过滤器是必要条件，不是加权打分。生意模式不喜欢或看不懂，就离开，不要往下找补
3. 差异化 = 用户需要但竞争对手满足不了的东西，不是「和别人不一样」，不是外观噱头
4. 判断差异化时必须把自己当消费者：自己会不会因为 5% 折扣换走
5. 每个结论必须引用预计算表或资料中的具体数字/事实；没有就写「数据未披露」，禁止编造
6. 规则引擎的「数字提示」禁止改写用词，只能解释依据。数字好不等于生意好，数字差通常先当苦生意
7. 禁止输出 Markdown 标题（不要写 #、##、###）。按编号逐条填写，不要增删条目
8. 关键数字用 **加粗**；最后单独一段，必须以「本章小结：」开头，2-3 句
9. 章节末尾必须另起一行写出指定的「过滤器判决」或「价格判决」或「综合态度」，只能用规定用词
"""

OUTPUT_CONTRACT = """输出要求（必须遵守）：
- 禁止输出 Markdown 标题（不要写 #、##、###）
- 禁止重复章节名，禁止写「解读」「原始数据」作为小标题
- 按下面编号 1. 2. 3. … 逐条填写，不要增删条目
- 每条必须引用表中数字或资料事实；缺数据写「数据未披露」
- 最后单独一段，以「本章小结：」开头，2-3 句
"""


def _base_context(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    numeric_hint: str,
    duan_summary: str,
    flags: list[str],
) -> str:
    flag_text = "\n".join(f"- {f}" for f in flags) if flags else "- 暂无重大数字警示"
    return f"""公司：{stock_name}（{stock_code}）
分析基准日：{data_cutoff_date}
数字提示（规则引擎判定，禁止改写）：{numeric_hint}

## 规则引擎预计算摘要
{duan_summary}

## 数字警示
{flag_text}
"""


def build_business_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    numeric_hint: str,
    duan_summary: str,
    flags: list[str],
    table: str,
    data_context: str,
    web_context: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, numeric_hint, duan_summary, flags)}

## 一、生意模式表（Python 预计算）
{table}

## 公司画像与分部
{data_context[:5000]}

## 联网补充（不得覆盖表内数字）
{web_context.strip() or "（本次无联网补充）"}

请填写「一、刮彩票：生意模式」。先看生意模式，刮到「谢」字就该离开。
1. 用一句话说清这门生意靠什么赚钱，谁付钱
2. 差异化是什么？必须回答：用户需要而竞争对手满足不了的是哪一点。没有就直说没有
3. 把自己当消费者：5% 折扣会不会换走？换走成本高不高
4. 引用长期毛利率、自由现金流、资产负债率，说明可替代性和净现金是否满意。数字提示是「{numeric_hint}」，禁止改写这个词
5. 十年后这门生意大概率还在不在？未来十年总利润有没有机会超过过去十年
6. 过滤器判决只能四选一：通过 / 存疑 / 离开 / 看不懂
   - 没有差异化、只能打价格战 → 离开
   - 自己看不清怎么赚钱、不敢毛估估十年现金流 → 看不懂
   - 数字一般但差异化说得通 → 存疑
   - 差异化清楚、长期现金说得通 → 通过

{OUTPUT_CONTRACT}
最后一行必须是：过滤器判决：通过 或 过滤器判决：存疑 或 过滤器判决：离开 或 过滤器判决：看不懂
"""


def build_culture_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    numeric_hint: str,
    duan_summary: str,
    flags: list[str],
    business_verdict: str,
    section_business: str,
    data_context: str,
    web_context: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, numeric_hint, duan_summary, flags)}

上一关生意模式判决：{business_verdict}

## 一章摘要
{section_business[:1500]}

## 公司与管理层相关资料
{data_context[:4000]}

## 联网补充
{web_context.strip() or "（本次无联网补充）"}

请填写「二、企业文化」。企业文化是护城河的一部分；不信任就离开，连报表都不必再看价钱。
1. 这帮人有没有「利润之上的追求」，还是利润至上
2. 是不是围着用户转（想用户需要什么，不是只会问用户要什么）
3. 本不本分：有没有急功近利、不健康扩张、明显不诚信的公开事实。没有证据不要扣帽子
4. 如果换个不太行的人来管，这门生意能扛一小会儿吗？文化能不能纠偏
5. 过滤器判决只能四选一：通过 / 存疑 / 离开 / 看不懂
   - 发现不本分、不信任 → 离开
   - 公开资料看不清文化 → 看不懂或存疑，不要假装看懂
   - 有用户导向、长期做事的证据 → 通过

{OUTPUT_CONTRACT}
最后一行必须是：过滤器判决：通过 或 过滤器判决：存疑 或 过滤器判决：离开 或 过滤器判决：看不懂
"""


def build_price_prompt(
    stock_name: str,
    stock_code: str,
    data_cutoff_date: str,
    numeric_hint: str,
    duan_summary: str,
    flags: list[str],
    business_verdict: str,
    culture_verdict: str,
    valuation_context: str,
) -> str:
    return f"""{_base_context(stock_name, stock_code, data_cutoff_date, numeric_hint, duan_summary, flags)}

生意模式：{business_verdict}；企业文化：{culture_verdict}
前两关已通过或存疑，这一章才看价钱。价钱是毛估估，不是精确内在价值。

## 估值与同业（只可引用此块数字）
{valuation_context.strip() or "（未采集到估值。价格判决写存疑意义上的「还行」或说明数据未披露，禁止用训练知识补 PE/市值。）"}

请填写「三、好价钱」。
1. 假设这不是上市公司，十年二十年都不交易，用现在的市值拥有它，你认不认
2. 只引用已有 PE/PB/市值等数字，说明贵不贵；禁止自造目标价、DCF 公式结果
3. PE 只是参考。关键仍是未来现金流，不是今年倍数
4. 价格判决只能四选一：便宜 / 还行 / 贵 / 跳过

{OUTPUT_CONTRACT}
最后一行必须是：价格判决：便宜 或 价格判决：还行 或 价格判决：贵 或 价格判决：跳过
"""


def build_synthesis_prompt(
    stock_name: str,
    stock_code: str,
    numeric_hint: str,
    locked_attitude: str,
    business_verdict: str,
    culture_verdict: str,
    price_verdict: str,
    diagnosis_table: str,
    section_business: str,
    section_culture: str,
    section_price: str,
) -> str:
    return f"""公司：{stock_name}（{stock_code}）
数字提示（禁止改写）：{numeric_hint}
生意模式：{business_verdict}；企业文化：{culture_verdict}；价格：{price_verdict}
综合态度已由过滤器锁定为「{locked_attitude}」，禁止改写成别的词。

## 综合诊断表
{diagnosis_table}

## 各章摘要
### 一、生意模式
{section_business[:1500]}

### 二、企业文化
{section_culture[:1200]}

### 三、价钱
{section_price[:1000]}

请填写「四、能不能看懂」。
1. 用段永平的标准回答：看懂 / 部分看懂 / 看不懂。看懂的意思是能毛估估未来净现金流，不是能复述主营业务
2. 三道过滤器各用一句话回顾，强调它们是必要条件不是加权分
3. 如果股市关十年，现在这个认知下你愿不愿意拿着（不是买卖建议，只描述认知）
4. 综合态度必须写「{locked_attitude}」，并给一句话理由（不超过 80 字）。禁止给出买入/卖出/目标价

{OUTPUT_CONTRACT}
最后一行必须是：综合态度：{locked_attitude}
"""


def build_assemble_header(
    stock_name: str,
    stock_code: str,
    industry: dict,
    data_cutoff_date: str,
    numeric_hint: str,
    business_verdict: str,
    culture_verdict: str,
    price_verdict: str,
    final_attitude: str,
) -> str:
    industry_name = industry.get("name") or industry.get("l3_name") or ""
    ind_part = f" | 行业：{industry_name}" if industry_name else ""
    return f"""# {stock_name}（{stock_code}）段永平看业务

> 分析基准日：{data_cutoff_date} | 数字提示：{numeric_hint}{ind_part}
> 过滤器：生意模式 **{business_verdict}** → 企业文化 **{culture_verdict}** → 价钱 **{price_verdict}**
> 综合态度：**{final_attitude}**（必要条件，不是打分加权）
> 框架：《大道》《何为道》· 先看生意模式，刮到谢字就停 · 数据：东财 F10 · 申万行业 · 联网补充
> 说明：不给买卖建议。看不懂或离开，就是流程的正常终点。
"""
