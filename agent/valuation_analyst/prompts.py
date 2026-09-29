"""估值智能体 Prompt：模型只解释规则引擎已算出的数字。"""

from __future__ import annotations

from typing import Any


SYSTEM = """你是 A 股估值助手。数字全部由规则引擎预先算出，你只解释假设，禁止改写、重算或发明任何市值、股价、倍数、分位、增速。
禁止给出买入/卖出点、仓位或「便宜就该买」。
三情景含义固定：悲观=更低隐含价值，中性=常态，乐观=更高隐含价值。
历史窗口是近 10 年 P25/P50/P75，不是历史最低/最高。
综合中性锚是历史/财报/收入因素三路中性市值的中位数；巴菲特中性只作安全边际下限，不能拿来拉高锚。
能力圈未确认时，不得写成「值得进一步研究」。
生意类型以规则引擎为准，禁止改写成别的类型。
报告正文已有规则表，你不要再抄整表。"""


def _lite_path(path: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in path.get("scenarios") or []:
        rows.append(
            {
                "name": row.get("name"),
                "mcap": row.get("mcap"),
                "price": row.get("price"),
                "upside": row.get("upside"),
                "formula": row.get("formula"),
                "na": row.get("na"),
            }
        )
    return {
        "label": path.get("label"),
        "primary": path.get("primary"),
        "weight": path.get("weight"),
        "notes": path.get("notes") or [],
        "scenarios": rows,
    }


def build_path_prompt(
    *,
    title: str,
    stock_name: str,
    stock_code: str,
    engine: dict[str, Any],
    path_key: str,
    extra: str = "",
) -> str:
    path = (engine.get("paths") or {}).get(path_key) or {}
    snap = engine.get("snap") or {}
    return f"""标的：{stock_name}（{stock_code}）
章节：{title}
现价 {snap.get("price")} · 市值 {snap.get("mcap")} · 主倍数 {engine.get("primary")} · 生意类型 {engine.get("business_type")}

本路预计算（禁止改数）：
{_lite_path(path)}

{engine.get("history_window_label") or "近10年"}分位摘要：{engine.get("stats")}
正常化盈利摘要：{engine.get("earned")}

{extra}

请写中文解读（不要章节大标题，不要表格），结构：
### 假设
### 三情景含义
### 本路可信度

要求：
- 点到公式里已有的数字即可，不要另造数字
- 说明何时本路该降权或作废
- 不超过 280 字
"""


def build_history_prompt(stock_name: str, stock_code: str, engine: dict[str, Any]) -> str:
    extra = "本路假设基本面维持现状，只让倍数沿近10年分位滑动。金融股应解释为何用 PB。"
    return build_path_prompt(
        title="一、历史倍数",
        stock_name=stock_name,
        stock_code=stock_code,
        engine=engine,
        path_key="history",
        extra=extra,
    )


def build_fundamentals_prompt(stock_name: str, stock_code: str, engine: dict[str, Any]) -> str:
    extra = "解释正常化盈利怎么来（扣非中位数/最差一年/CAGR 封顶 15%）。自由现金流持续为负时不要改用 FCF 作价。"
    return build_path_prompt(
        title="二、财报正常化",
        stock_name=stock_name,
        stock_code=stock_code,
        engine=engine,
        path_key="fundamentals",
        extra=extra,
    )


def build_buffett_prompt(stock_name: str, stock_code: str, engine: dict[str, Any]) -> str:
    extra = "要求回报率悲观12%/中性10%/乐观8%；安全边际悲观70%、中性80%、乐观仅伟大可为100%。平庸/糟糕乐观不得高于中性。下沿未披露时不得用上沿冒充。"
    return build_path_prompt(
        title="三、巴菲特",
        stock_name=stock_name,
        stock_code=stock_code,
        engine=engine,
        path_key="buffett",
        extra=extra,
    )


def build_drivers_prompt(
    stock_name: str,
    stock_code: str,
    engine: dict[str, Any],
    segment_text: str,
) -> str:
    extra = f"""收入关键因素占位：营收冲击 × 净利率分位，退出倍数固定中性分位。
你必须点名 1～3 个真正拉动收入的因素（来自分部/生意，不要宏观百科）。弹性说不清的因素不要假装能量化。
主营分部摘录：
{(segment_text or "（无分部）")[:2500]}
"""
    return build_path_prompt(
        title="四、收入关键因素",
        stock_name=stock_name,
        stock_code=stock_code,
        engine=engine,
        path_key="drivers",
        extra=extra,
    )


def build_synthesis_prompt(stock_name: str, stock_code: str, engine: dict[str, Any]) -> str:
    composite = engine.get("composite") or {}
    return f"""标的：{stock_name}（{stock_code}）
综合预计算（禁止改数）：
态度：{composite.get("stance")}
综合中性锚市值：{composite.get("anchor_mid_mcap")}
综合中性锚股价：{composite.get("anchor_mid_price")}
巴菲特安全边际下限：{composite.get("mos_floor_mcap")} / {composite.get("mos_floor_price")}
作废条件：{composite.get("invalidation")}
备注：{composite.get("notes")}
四路摘要：{ {k: _lite_path(v) for k, v in (engine.get("paths") or {}).items()} }

请写交叉对照（不要大标题，不要表格）：
### 哪一路更可信
### 现价落在什么位置
### 综合态度为何是「{composite.get("stance")}」
### 失效观察

要求：
- 态度必须与规则引擎一致，不得改成别的词
- 不超过 320 字
"""
