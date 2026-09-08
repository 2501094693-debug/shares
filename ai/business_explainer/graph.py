"""业务简述智能体 — LangGraph 工作流。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from business_explainer.nodes import (
    fetch_data,
    generate_explanation,
    init_company,
    save_explanation,
)
from business_explainer.state import BusinessExplainerState


def build_graph() -> StateGraph:
    """流程: 解析公司 → 采集资料 → 生成解读 → 保存。"""
    graph = StateGraph(BusinessExplainerState)

    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_data)
    graph.add_node("explain", generate_explanation)
    graph.add_node("save", save_explanation)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "explain")
    graph.add_edge("explain", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
