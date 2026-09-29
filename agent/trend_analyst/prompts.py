"""趋势分析智能体 — Prompt。"""

from __future__ import annotations

import json
from typing import Any


SYSTEM = """你是 A 股短线资金与分时成交分析助手。
只根据给定的资金动向列表（同花顺大单）与分时成交列表规则摘要写解读，不要编造未提供的数字。
报告正文已有「数据统计」节，你只写分析，不要再整段罗列统计表。
禁止使用日线、均线、形态、量比、东财分档主力净额等未提供的内容。
禁止给出具体买入/卖出点位、仓位或「必涨/必跌」表述。
散户数量是小单活跃度代理，必须写明不是真实持仓人数。
资金单位若摘要里是「亿」，保持一致。"""


def build_synthesis_prompt(
    stock_name: str,
    stock_code: str,
    day: str,
    fund: dict[str, Any],
    ticks: dict[str, Any],
    verdict: dict[str, Any],
) -> str:
    fund_lite = {
        k: fund.get(k)
        for k in (
            "label",
            "evidence",
            "big_deal_count",
            "active_buy_share",
            "active_buy_yi",
            "active_sell_yi",
            "net_active_yi",
            "streak",
            "deal_sessions",
            "top_events",
        )
        if k in fund
    }
    ticks_lite = {
        k: ticks.get(k)
        for k in (
            "activity",
            "stance",
            "relation_to_main",
            "tick_count",
            "buy_share",
            "small_trade_count",
            "small_buy_share",
            "small_net_yi",
            "pct_vs_pre",
            "peak_session",
            "cross_evidence",
            "deal_coverage",
            "evidence",
            "note",
        )
        if k in ticks
    }
    payload = {"fund": fund_lite, "ticks": ticks_lite, "verdict": verdict}
    return f"""标的：{stock_name}（{stock_code}），数据日：{day or "最近交易日"}。

规则摘要 JSON（数字已在报告「数据统计」列出）：
{json.dumps(payload, ensure_ascii=False, indent=2)}

请写中文**分析解读**（不要写「数据统计」或「分析解读」标题，不要表格），结构固定（三级标题）：
### 综合结论
### 资金动向解读
### 分时成交解读
### 博弈含义与失效观察

要求：
- 「综合结论」先给 lean + 置信度，再 2～3 句说明共振/背离
- 各段关键数字点到为止（每段最多 1～2 个）
- 样本不足时明确说明
- 全文不超过 400 字
"""
