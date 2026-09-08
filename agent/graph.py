"""LangGraph 投研团队工作流定义。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from nodes import (
    init_research,
    run_business_analyst,
    run_financial_analyst,
    run_industry_researcher,
    run_risk_assessor,
    run_audit_extract,
    save_report,
    synthesize_report,
)
from state import InvestmentTeamState


def fan_out_analysts(state: InvestmentTeamState) -> list[Send]:
    """并行启动 4 个分析师（对应 SKILL 第四步）。"""
    return [
        Send("business_analyst", state),
        Send("financial_analyst", state),
        Send("industry_researcher", state),
        Send("risk_assessor", state),
    ]


def build_graph() -> StateGraph:
    graph = StateGraph(InvestmentTeamState)

    graph.add_node("init", init_research)
    graph.add_node("business_analyst", run_business_analyst)
    graph.add_node("financial_analyst", run_financial_analyst)
    graph.add_node("industry_researcher", run_industry_researcher)
    graph.add_node("risk_assessor", run_risk_assessor)
    graph.add_node("team_lead", synthesize_report)
    graph.add_node("save", save_report)
    graph.add_node("audit", run_audit_extract)

    graph.add_edge(START, "init")
    graph.add_conditional_edges("init", fan_out_analysts)

    graph.add_edge(
        ["business_analyst", "financial_analyst", "industry_researcher", "risk_assessor"],
        "team_lead",
    )
    graph.add_edge("team_lead", "save")
    graph.add_edge("save", "audit")
    graph.add_edge("audit", END)

    return graph


def compile_app():
    return build_graph().compile()
