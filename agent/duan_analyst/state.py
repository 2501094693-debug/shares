"""段永平看业务智能体 — 状态定义。"""

from __future__ import annotations

from typing import Any, TypedDict


class DuanAnalystState(TypedDict, total=False):
    """段永平看业务流程状态。过滤器是必要条件，可中途离开。"""

    company: str
    data_cutoff_date: str
    stock_code: str
    stock_name: str
    stock_market: str
    industry: dict[str, Any]
    stock: dict[str, Any]

    data_context: str
    web_context: str
    web_engines: list[str]
    web_search_used: bool
    sources_used: list[str]
    data_available: bool
    errors: list[str]

    duan_metrics: dict[str, Any]
    duan_flags: list[str]
    duan_tables: dict[str, str]
    duan_summary: str
    numeric_hint: str

    business_verdict: str
    culture_verdict: str
    price_verdict: str
    understand_verdict: str
    final_attitude: str
    skip_reason: str

    section_business: str
    section_culture: str
    section_price: str
    section_synthesis: str

    final_report: str
    report: str
    report_path: str
