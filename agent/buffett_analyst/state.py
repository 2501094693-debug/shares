"""巴菲特读表智能体 — 状态定义。"""

from __future__ import annotations

from typing import Any, TypedDict


class BuffettAnalystState(TypedDict, total=False):
    """巴菲特读表工作流状态。"""

    company: str
    data_cutoff_date: str
    stock_code: str
    stock_name: str
    stock_market: str
    industry: dict[str, Any]
    stock: dict[str, Any]

    data_context: str
    sources_used: list[str]
    data_available: bool
    errors: list[str]

    buffett_metrics: dict[str, Any]
    buffett_flags: list[str]
    buffett_tables: dict[str, str]
    buffett_summary: str
    business_type: str

    section_understand: str
    section_owner: str
    section_capital: str
    section_honesty: str
    section_synthesis: str

    final_report: str
    report: str
    report_path: str
