"""散户情绪智能体 — Prompt。"""

from __future__ import annotations

CLASSIFY_SYSTEM = """你在给 A 股个股社区评论打标签。评论来自东方财富股吧、同花顺讨论、雪球。
只根据给定文本判断，不要编造未出现的信息。

对每条评论输出：
- stance: bull（看多） / bear（看空） / mixed（多空都有或自我矛盾） / unclear（看不出立场）
- action: buy（买入或加仓） / sell（卖出、减仓、清仓、割肉） / wait（观望、持币、躺平、等回调） / none（没有行动意图）
- confidence: 0 到 1
- is_retail: 是否像普通散户。媒体、官号、研报、广告、明显水军为 false

规则：
- 「明天买」「加仓」→ action=buy；「割了」「清仓」→ sell；「再看看」「等回调」→ wait
- 看多却在卖 → stance=bull, action=sell
- 脏话发泄但无方向 → unclear / none
- 只转发公告、研报标题 → is_retail=false，stance=unclear
只输出 JSON，不要 markdown。"""


def build_classify_prompt(stock_name: str, stock_code: str, batch: list[dict]) -> str:
    lines = [
        f"标的：{stock_name}（{stock_code}）",
        "请标注下列评论。返回 JSON 对象：",
        '{"labels":[{"id":"...","stance":"bull|bear|mixed|unclear","action":"buy|sell|wait|none","confidence":0.0,"is_retail":true}]}',
        "id 必须与输入完全一致。",
        "",
    ]
    for row in batch:
        text = (row.get("text") or "").replace("\n", " ").strip()[:400]
        lines.append(f"- id={row.get('id')} author={row.get('author') or ''} text={text}")
    return "\n".join(lines)


def build_synthesis_prompt(
    stock_name: str,
    stock_code: str,
    days: int,
    metrics: dict,
    platform_scores: dict,
) -> str:
    return f"""根据下列「发声散户」统计写 4～6 句中文解读。这是评论样本上的情绪估计，不是真实持仓或成交。
禁止给出买入/卖出建议。若样本很少，明确说不可外推。

公司：{stock_name}（{stock_code}），窗口近 {days} 天。
指标：{metrics}
平台快照（千股千评/热度，仅对照）：{platform_scores}

写清：散户人数口径、看多还是看空、买卖观望结构、三源是否同向、和平台快照是否打架。"""
