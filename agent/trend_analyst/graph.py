"""趋势分析智能体 — LangGraph 工作流（仅资金 + 分时）。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.trend_analyst.nodes import (
    analyze_main,
    analyze_retail_node,
    fetch_pack,
    init_company,
    save_report,
    synthesize,
)
from agent.trend_analyst.state import TrendState


def build_graph() -> StateGraph:
    """解析 → 拉数 → 资金统计 → 分时统计 → 综合 → 保存。"""
    graph = StateGraph(TrendState)

    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_pack)
    graph.add_node("main", analyze_main)
    graph.add_node("retail", analyze_retail_node)
    graph.add_node("synthesize", synthesize)
    graph.add_node("save", save_report)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "main")
    graph.add_edge("main", "retail")
    graph.add_edge("retail", "synthesize")
    graph.add_edge("synthesize", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
