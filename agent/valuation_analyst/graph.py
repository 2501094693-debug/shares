"""估值分析智能体 — LangGraph 工作流。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.valuation_analyst.nodes import (
    analyze_buffett,
    analyze_drivers,
    analyze_fundamentals,
    analyze_history,
    fetch_pack,
    init_company,
    save_report,
    synthesize,
)
from agent.valuation_analyst.state import ValuationState


def build_graph() -> StateGraph:
    graph = StateGraph(ValuationState)
    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_pack)
    graph.add_node("history", analyze_history)
    graph.add_node("fundamentals", analyze_fundamentals)
    graph.add_node("buffett", analyze_buffett)
    graph.add_node("drivers", analyze_drivers)
    graph.add_node("synthesize", synthesize)
    graph.add_node("save", save_report)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "history")
    graph.add_edge("history", "fundamentals")
    graph.add_edge("fundamentals", "buffett")
    graph.add_edge("buffett", "drivers")
    graph.add_edge("drivers", "synthesize")
    graph.add_edge("synthesize", "save")
    graph.add_edge("save", END)
    return graph


def compile_app():
    return build_graph().compile()
