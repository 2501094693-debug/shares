"""段永平看业务智能体 — LangGraph 工作流。

先看生意模式；刮到谢字（离开/看不懂）就不再看企业文化与价钱。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.duan_analyst.nodes import (
    assemble_report,
    fetch_data,
    filter_business,
    filter_culture,
    filter_price,
    init_company,
    save_report,
    skip_after_business,
    skip_after_culture,
    synthesize,
)
from agent.duan_analyst.rules import should_continue_after_business, should_continue_after_culture
from agent.duan_analyst.state import DuanAnalystState


def route_after_business(state: DuanAnalystState) -> str:
    if should_continue_after_business(state.get("business_verdict") or ""):
        return "filter_culture"
    return "skip_after_business"


def route_after_culture(state: DuanAnalystState) -> str:
    if should_continue_after_culture(state.get("culture_verdict") or ""):
        return "filter_price"
    return "skip_after_culture"


def build_graph() -> StateGraph:
    """流程: 解析 → 采集+数字预计算 → 生意模式 → [过则看文化] → [过则看价钱] → 综合 → 保存。"""
    graph = StateGraph(DuanAnalystState)

    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_data)
    graph.add_node("filter_business", filter_business)
    graph.add_node("filter_culture", filter_culture)
    graph.add_node("filter_price", filter_price)
    graph.add_node("skip_after_business", skip_after_business)
    graph.add_node("skip_after_culture", skip_after_culture)
    graph.add_node("synthesis", synthesize)
    graph.add_node("assemble", assemble_report)
    graph.add_node("save", save_report)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "filter_business")
    graph.add_conditional_edges(
        "filter_business",
        route_after_business,
        {
            "filter_culture": "filter_culture",
            "skip_after_business": "skip_after_business",
        },
    )
    graph.add_conditional_edges(
        "filter_culture",
        route_after_culture,
        {
            "filter_price": "filter_price",
            "skip_after_culture": "skip_after_culture",
        },
    )
    graph.add_edge("filter_price", "synthesis")
    graph.add_edge("skip_after_business", "synthesis")
    graph.add_edge("skip_after_culture", "synthesis")
    graph.add_edge("synthesis", "assemble")
    graph.add_edge("assemble", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
