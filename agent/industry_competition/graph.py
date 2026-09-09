"""行业竞争分析智能体 — LangGraph 工作流。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from industry_competition.nodes import (
    fetch_data,
    generate_analysis,
    init_company,
    save_report,
    search_web_supplement,
)
from industry_competition.state import IndustryCompetitionState


def build_graph() -> StateGraph:
    """流程: 解析公司 → 官方披露 → 联网补充 → 生成分析 → 保存。"""
    graph = StateGraph(IndustryCompetitionState)

    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_data)
    graph.add_node("search", search_web_supplement)
    graph.add_node("analyze", generate_analysis)
    graph.add_node("save", save_report)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "search")
    graph.add_edge("search", "analyze")
    graph.add_edge("analyze", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
