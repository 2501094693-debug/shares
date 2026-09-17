"""张新民「八看」财报解读智能体 — 状态定义。"""

from __future__ import annotations

from typing import Any, TypedDict


class BazhangAnalystState(TypedDict, total=False):
    """八看工作流状态。"""

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

    zhang_metrics: dict[str, Any]
    zhang_flags: list[str]
    zhang_tables: dict[str, str]
    zhang_summary: str
    strategy_type: str

    section_strategy: str
    section_operating: str
    section_profit: str
    section_value: str
    section_cost: str
    section_quality: str
    section_risk: str
    section_outlook: str
    section_synthesis: str

    final_report: str
    report: str
    report_path: str
