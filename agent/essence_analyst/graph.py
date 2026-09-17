"""生意本质智能体：起草 ↔ 质疑循环，不是单向流水线。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.essence_analyst.nodes import (
    advance_node,
    assemble_node,
    critique_node,
    extra_search_node,
    fetch_official_node,
    fetch_web_node,
    resolve_company_node,
    save_node,
    write_node,
)
from agent.essence_analyst.stages import route_after_advance, route_after_critique
from agent.essence_analyst.state import EssenceState

RECURSION_LIMIT = 80


def build_graph() -> StateGraph:
    graph = StateGraph(EssenceState)
    graph.add_node("resolve", resolve_company_node)
    graph.add_node("fetch_official", fetch_official_node)
    graph.add_node("fetch_web", fetch_web_node)
    graph.add_node("extra_search", extra_search_node)
    graph.add_node("write", write_node)
    graph.add_node("critique", critique_node)
    graph.add_node("advance", advance_node)
    graph.add_node("assemble", assemble_node)
    graph.add_node("save", save_node)

    graph.add_edge(START, "resolve")
    graph.add_edge("resolve", "fetch_official")
    graph.add_edge("fetch_official", "write")
    graph.add_edge("write", "critique")
    graph.add_conditional_edges(
        "critique",
        route_after_critique,
        {
            "write": "write",
            "extra_search": "extra_search",
            "advance": "advance",
        },
    )
    graph.add_edge("extra_search", "write")
    graph.add_conditional_edges(
        "advance",
        route_after_advance,
        {
            "write": "write",
            "fetch_web": "fetch_web",
            "assemble": "assemble",
        },
    )
    graph.add_edge("fetch_web", "write")
    graph.add_edge("assemble", "save")
    graph.add_edge("save", END)
    return graph


def compile_app():
    return build_graph().compile()
