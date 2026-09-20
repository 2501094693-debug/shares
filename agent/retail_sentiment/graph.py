"""散户情绪智能体 — LangGraph 工作流。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.retail_sentiment.nodes import (
    aggregate,
    classify_comments,
    fetch_em,
    fetch_ths,
    fetch_xq,
    filter_retail,
    init_company,
    merge_corpus,
    save_report,
    synthesize,
)
from agent.retail_sentiment.state import RetailSentimentState


def build_graph() -> StateGraph:
    """解析 → 三源并行采集 → 合并过滤 → 标注 → 按人计数 → 解读 → 保存。"""
    graph = StateGraph(RetailSentimentState)

    graph.add_node("init", init_company)
    graph.add_node("fetch_em", fetch_em)
    graph.add_node("fetch_ths", fetch_ths)
    graph.add_node("fetch_xq", fetch_xq)
    graph.add_node("merge", merge_corpus)
    graph.add_node("filter", filter_retail)
    graph.add_node("classify", classify_comments)
    graph.add_node("aggregate", aggregate)
    graph.add_node("synthesize", synthesize)
    graph.add_node("save", save_report)

    graph.add_edge(START, "init")
    graph.add_edge("init", "fetch_em")
    graph.add_edge("init", "fetch_ths")
    graph.add_edge("init", "fetch_xq")
    graph.add_edge("fetch_em", "merge")
    graph.add_edge("fetch_ths", "merge")
    graph.add_edge("fetch_xq", "merge")
    graph.add_edge("merge", "filter")
    graph.add_edge("filter", "classify")
    graph.add_edge("classify", "aggregate")
    graph.add_edge("aggregate", "synthesize")
    graph.add_edge("synthesize", "save")
    graph.add_edge("save", END)

    return graph


def compile_app():
    return build_graph().compile()
