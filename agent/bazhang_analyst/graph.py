"""张新民「八看」财报解读智能体 — LangGraph 工作流。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.bazhang_analyst.nodes import (
    analyze_cost,
    analyze_operating,
    analyze_outlook,
    analyze_profit,
    analyze_quality,
    analyze_risk,
    analyze_strategy,
    analyze_value,
    assemble_report,
    fetch_data,
    init_company,
    save_report,
    synthesize,
)
from agent.bazhang_analyst.state import BazhangAnalystState


def build_graph() -> StateGraph:
    """流程: 解析 → 采集+规则引擎 → 八看逐章解读 → 综合诊断 → 拼装 → 保存。"""
    graph = StateGraph(BazhangAnalystState)

    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_data)
    graph.add_node("strategy", analyze_strategy)
    graph.add_node("operating", analyze_operating)
    graph.add_node("profit", analyze_profit)
    graph.add_node("value", analyze_value)
    graph.add_node("cost", analyze_cost)
    graph.add_node("quality", analyze_quality)
    graph.add_node("risk", analyze_risk)
    graph.add_node("outlook", analyze_outlook)
    graph.add_node("synthesis", synthesize)
    graph.add_node("assemble", assemble_report)
    graph.add_node("save", save_report)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "strategy")
    graph.add_edge("strategy", "operating")
    graph.add_edge("operating", "profit")
    graph.add_edge("profit", "value")
    graph.add_edge("value", "cost")
    graph.add_edge("cost", "quality")
    graph.add_edge("quality", "risk")
    graph.add_edge("risk", "outlook")
    graph.add_edge("outlook", "synthesis")
    graph.add_edge("synthesis", "assemble")
    graph.add_edge("assemble", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
