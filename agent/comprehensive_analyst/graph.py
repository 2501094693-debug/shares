"""综合深度研判智能体 — LangGraph 工作流。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.comprehensive_analyst.nodes import (
    analyze_balance,
    analyze_business,
    analyze_cashflow,
    analyze_income,
    analyze_outlook,
    analyze_valuation,
    assemble_report,
    fetch_data,
    init_company,
    save_report,
    search_market,
    synthesize_financials,
)
from agent.comprehensive_analyst.state import ComprehensiveAnalystState


def build_graph() -> StateGraph:
    """流程: 解析 → 采集 → 业务 → 三表 → 汇总 → 估值 → 市场 → 前景 → 拼装 → 保存。"""
    graph = StateGraph(ComprehensiveAnalystState)

    graph.add_node("init", init_company)
    graph.add_node("fetch", fetch_data)
    graph.add_node("business", analyze_business)
    graph.add_node("balance", analyze_balance)
    graph.add_node("income", analyze_income)
    graph.add_node("cashflow", analyze_cashflow)
    graph.add_node("synthesis", synthesize_financials)
    graph.add_node("valuation", analyze_valuation)
    graph.add_node("search", search_market)
    graph.add_node("outlook", analyze_outlook)
    graph.add_node("assemble", assemble_report)
    graph.add_node("save", save_report)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch")
    graph.add_edge("fetch", "business")
    graph.add_edge("business", "balance")
    graph.add_edge("balance", "income")
    graph.add_edge("income", "cashflow")
    graph.add_edge("cashflow", "synthesis")
    graph.add_edge("synthesis", "valuation")
    graph.add_edge("valuation", "search")
    graph.add_edge("search", "outlook")
    graph.add_edge("outlook", "assemble")
    graph.add_edge("assemble", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
