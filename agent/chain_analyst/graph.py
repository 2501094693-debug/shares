"""产业链分析智能体 — LangGraph 工作流。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.chain_analyst.nodes import (
    fetch_data,
    generate_analysis,
    init_company,
    map_chain,
    save_report,
    search_layers,
)
from agent.chain_analyst.state import ChainAnalystState


def build_graph() -> StateGraph:
    """流程: 解析公司 → 官方披露 → 绘制地图 → 定向检索 → 生成分析 → 保存。"""
    graph = StateGraph(ChainAnalystState)

    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_data)
    graph.add_node("map_chain", map_chain)
    graph.add_node("search_layers", search_layers)
    graph.add_node("analyze", generate_analysis)
    graph.add_node("save", save_report)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "map_chain")
    graph.add_edge("map_chain", "search_layers")
    graph.add_edge("search_layers", "analyze")
    graph.add_edge("analyze", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
