"""近一年财报解读智能体 — LangGraph 工作流。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.earnings_reviewer.nodes import fetch_data, generate_review, init_company, save_review
from agent.earnings_reviewer.state import EarningsReviewerState


def build_graph() -> StateGraph:
    """流程: 解析公司 → 采集财报 → 生成解读 → 保存。"""
    graph = StateGraph(EarningsReviewerState)

    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_data)
    graph.add_node("explain", generate_review)
    graph.add_node("save", save_review)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "explain")
    graph.add_edge("explain", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
