"""综合深度研判智能体 — 状态定义。"""

from __future__ import annotations

from typing import Any, TypedDict


class ComprehensiveAnalystState(TypedDict, total=False):
    """综合研判工作流状态。"""

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

    balance_rules_text: str
    income_rules_text: str
    cashflow_rules_text: str
    valuation_scenarios_text: str
    mda_text: str

    business_analysis: str
    key_drivers: list[dict[str, Any]]
    balance_analysis: str
    income_analysis: str
    cashflow_analysis: str
    financial_synthesis: str
    valuation_report: str
    market_intel: str
    outlook_report: str

    final_report: str
    report: str
    report_path: str
