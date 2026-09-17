"""巴菲特读表智能体 — LangGraph 工作流。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.buffett_analyst.nodes import (
    analyze_capital,
    analyze_honesty,
    analyze_owner,
    analyze_understand,
    assemble_report,
    fetch_data,
    init_company,
    save_report,
    synthesize,
)
from agent.buffett_analyst.state import BuffettAnalystState


def build_graph() -> StateGraph:
    """流程: 解析 → 采集+规则引擎 → 四章解读 → 综合判决 → 拼装 → 保存。"""
    graph = StateGraph(BuffettAnalystState)

    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_data)
    graph.add_node("understand", analyze_understand)
    graph.add_node("owner_earnings", analyze_owner)
    graph.add_node("capital_type", analyze_capital)
    graph.add_node("accounting_alloc", analyze_honesty)
    graph.add_node("synthesis", synthesize)
    graph.add_node("assemble", assemble_report)
    graph.add_node("save", save_report)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "understand")
    graph.add_edge("understand", "owner_earnings")
    graph.add_edge("owner_earnings", "capital_type")
    graph.add_edge("capital_type", "accounting_alloc")
    graph.add_edge("accounting_alloc", "synthesis")
    graph.add_edge("synthesis", "assemble")
    graph.add_edge("assemble", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
