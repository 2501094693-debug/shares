"""阶段顺序、路由。纯函数，供图与测试共用。"""

from __future__ import annotations

from typing import Any

MAX_ROUNDS = 3
MAX_EXTRA_SEARCH = 1

STAGES: tuple[str, ...] = (
    "businesses",
    "explain",
    "factors",
)

STAGE_AGENT: dict[str, str] = {
    "businesses": "es_businesses",
    "explain": "es_explain",
    "factors": "es_factors",
}

STAGE_TITLE: dict[str, str] = {
    "businesses": "主营业务（官方）",
    "explain": "这些业务究竟干什么",
    "factors": "关键影响因素",
}


def next_stage(stage: str) -> str | None:
    if stage not in STAGES:
        return STAGES[0]
    index = STAGES.index(stage)
    if index + 1 >= len(STAGES):
        return None
    return STAGES[index + 1]


def route_after_critique(state: dict[str, Any]) -> str:
    """质疑之后：补证据 / 退回重写 / 进入下一段。"""
    verdict = (state.get("critique_verdict") or "confirm").strip()
    rnd = int(state.get("round") or 1)
    extras = int(state.get("extra_searches") or 0)
    if verdict in {"confirm", "exhausted"} or rnd >= MAX_ROUNDS:
        return "advance"
    if verdict == "need_evidence" and extras < MAX_EXTRA_SEARCH:
        return "extra_search"
    if verdict in {"revise", "need_evidence"}:
        return "write"
    return "advance"


def route_after_advance(state: dict[str, Any]) -> str:
    """advance 节点已经把 stage 切到下一章（或 all_done）。"""
    if state.get("all_done"):
        return "assemble"
    stage = str(state.get("stage") or "")
    if stage == "explain" and not state.get("web_fetched"):
        return "fetch_web"
    return "write"
