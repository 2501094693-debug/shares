"""生意本质智能体状态。"""

from __future__ import annotations

from typing import Any, TypedDict


class EssenceState(TypedDict, total=False):
    company: str
    stock_code: str
    stock_name: str
    market: str
    data_cutoff: str
    official_text: str
    web_text: str
    extra_text: str
    sources_used: list[str]
    errors: list[str]
    stage: str
    round: int
    extra_searches: int
    draft: str
    critique_verdict: str
    critique_issues: list[str]
    critique_fix: str
    search_query: str
    search_scope: str
    chapters: dict[str, str]
    confirm_log: list[dict[str, Any]]
    web_fetched: bool
    all_done: bool
    final_report: str
    report_path: str
