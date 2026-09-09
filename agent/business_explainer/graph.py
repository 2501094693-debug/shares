"""业务简述智能体 — LangGraph 工作流。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.business_explainer.nodes import (
    fetch_data,
    generate_explanation,
    init_company,
    save_explanation,
    search_web_supplement,
)
from agent.business_explainer.state import BusinessExplainerState


def build_graph() -> StateGraph:
    """流程: 解析公司 → 官方披露 → 联网补充 → 生成解读 → 保存。"""
    graph = StateGraph(BusinessExplainerState)

    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_data)
    graph.add_node("search", search_web_supplement)
    graph.add_node("explain", generate_explanation)
    graph.add_node("save", save_explanation)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "search")
    graph.add_edge("search", "explain")
    graph.add_edge("explain", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
