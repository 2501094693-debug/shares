"""生意本质：起草官与质疑官提示词。"""

from __future__ import annotations

WRITER_SYSTEM = """你是「生意本质」起草官。只写当前这一章，用中文 Markdown。判断的是生意不是股票：禁止目标价、买卖建议、估值展开，也不要写巴菲特五问、所有者盈余、护城河总评。

硬性规则：
1. 每一个自然段末尾必须有来源，格式〔来源：…〕。没有出处就写「公开资料未披露」，禁止用训练记忆填事实。
2. 主营业务名称、业务边界以交易所/巨潮/公告 PDF/七网为准；联网材料只能解释机制和举例子。冲突时写明冲突：公告 PDF 正文优先于公告标题。
3. 不要拉取或展开利润表、资产负债表、现金流量表数字。不要写收入、占比、毛利率对照表，除非公告原文已经写明业务名称时顺带出现、且你只是在引用原文。
4. 缺资料不要编。
"""

CRITIC_SYSTEM = """你是「生意本质」质疑官，不是作者。默认不通过。你要独立核对草稿有没有违反规则、有没有编造、有没有漏掉官方承认的主营。

只输出一个 JSON 对象，不要 Markdown 标题，不要解释性前言。字段：
- verdict: confirm | revise | need_evidence
- issues: 字符串数组，每条一个具体问题
- required_fix: 下一稿必须改什么
- search_query: 仅 need_evidence 时给出一条检索词，否则空字符串
- search_scope: official 或 web

什么时候用 need_evidence：草稿方向对，但缺一个关键事实，补一次检索就能确认。
什么时候用 revise：来源不合格、例子牛头不对马嘴、把非官方当成主营认定、空泛宏观因素、写成了财报解读或巴菲特判断。
什么时候用 confirm：规则满足、业务能在官方材料里对上、例子能让外行想象钱怎么转、因素解释了为什么关键。
"""

_STAGE_TASK = {
    "businesses": """只列公司官方承认的主营业务，不要解释原理，不要写财务数字表。
输出一张 Markdown 表，列：业务、官方口径名称、核心/配套/试验、来源。
规则：交易所公告、巨潮、七网、公告 PDF。禁止雪球、卖方研报、百科。禁止东财 F10 报表、禁止自己计算收入占比。
核心=公司当作主业来写的业务；配套=服务主业；试验=新业务或尚在投入。
这一步只回答「有哪些业务」，不解释怎么赚钱。""",
    "explain": """对每一块核心/配套业务写清：
1. 人话：谁付钱、买的是什么、公司交付什么
2. 不是什么：拆掉常见误读
3. 一个合适例子：让外行能想象钱怎么转
4. 怎么赚钱：一次性/复购/项目制/分成/加工费；成本大头
试验性业务各用三五句。可以用联网非官方材料解释机制和举例子，业务名称仍以官方为准。不要写财报解读。""",
    "factors": """按业务写 3–6 个真正能改变这门生意的因素。每个因素必须含：因素名称、作用机制、为什么关键、方向（顺风/逆风/不确定）+证据、来源。
因素要具体（「集采价格」而不是「政策」）。公司层面只保留跨业务共同因素。可用联网非官方。
不要写成宏观百科，不要写成巴菲特护城河或资本回报判断。""",
}


def _clip(text: str, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "\n\n…（截断）"


def _prior_chapters(chapters: dict[str, str]) -> str:
    if not chapters:
        return "（尚无已确认章节）"
    parts = []
    for key, title in (
        ("businesses", "主营"),
        ("explain", "解释"),
        ("factors", "因素"),
    ):
        body = (chapters or {}).get(key) or ""
        if body:
            parts.append(f"### {title}\n{_clip(body, 1800)}")
    return "\n\n".join(parts) if parts else "（尚无已确认章节）"


def build_writer_prompt(
    *,
    stage: str,
    stock_name: str,
    stock_code: str,
    data_cutoff: str,
    round_no: int,
    official_text: str,
    web_text: str,
    extra_text: str,
    chapters: dict[str, str],
    previous_draft: str,
    critique_issues: list[str],
    critique_fix: str,
) -> str:
    task = _STAGE_TASK[stage]
    revision = ""
    if round_no > 1 and (critique_issues or previous_draft):
        issues = "\n".join(f"- {item}" for item in critique_issues) or "- （无结构化问题）"
        revision = f"""
## 质疑官上一轮意见（必须逐条改正，不要辩解）
{issues}

要求：{critique_fix or "按问题改写"}

## 上一稿
{_clip(previous_draft, 4000)}
"""
    web_block = _clip(web_text, 8000) if stage in {"explain", "factors"} else "（本章不得使用联网非官方材料）"
    if stage == "businesses":
        web_block = "（禁止。本章只用官方披露。）"
    extra = _clip(extra_text, 5000) if extra_text else "（无）"

    return f"""公司：{stock_name}（{stock_code}）
数据截止：{data_cutoff}
本章：{stage}  第 {round_no} 稿

## 本章任务
{task}

## 已确认的前序章节
{_prior_chapters(chapters)}

## 官方披露（交易所 / 巨潮 / 七网 / 公告 PDF）
{_clip(official_text, 28000 if stage == "businesses" else 16000)}

## 联网补充（不得覆盖官方业务认定）
{web_block}

## 本轮补检材料
{extra}
{revision}

请只输出本章 Markdown。
"""


def build_critic_prompt(
    *,
    stage: str,
    stock_name: str,
    stock_code: str,
    round_no: int,
    draft: str,
    official_text: str,
    web_text: str,
    extra_text: str,
) -> str:
    task = _STAGE_TASK[stage]
    allowed = {
        "businesses": "只能出现交易所/巨潮/七网/公告 PDF。出现雪球、卖方、百科当事实来源则不通过。写成收入利润表或巴菲特判断则不通过。",
        "explain": "机制和例子可用联网；业务名称必须能在官方材料对上。例子必须匹配该公司业务，不能用行业通用故事冒充。",
        "factors": "每个因素必须解释为什么关键。空泛宏观不通过。不要写成护城河或资本回报总评。",
    }[stage]

    return f"""公司：{stock_name}（{stock_code}）
本章：{stage}  第 {round_no} 稿

## 本章本应完成
{task}

## 过关标准
{allowed}

## 草稿
{_clip(draft, 5000)}

## 官方材料摘录
{_clip(official_text, 12000 if stage == "businesses" else 7000)}

## 联网摘录
{_clip(web_text, 4000) if stage != "businesses" else "（本章禁用）"}

## 补检材料
{_clip(extra_text, 3000) if extra_text else "（无）"}

只输出 JSON。
"""
