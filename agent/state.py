"""LangGraph 共享状态定义。"""

import operator
from typing import Annotated, Literal, TypedDict


InfoRichnessLevel = Literal["A", "B", "C"]


class AnalystReport(TypedDict):
    role: str
    role_cn: str
    framework: str
    subject: str
    content: str
    score: float | None
    web_search_used: bool
    confidence_note: str


class InvestmentTeamState(TypedDict):
    """投研团队工作流状态。"""

    company: str
    user_request: str

    data_cutoff_date: str
    info_richness: InfoRichnessLevel
    info_richness_rationale: str
    web_search_available: bool

    stock_code: str
    stock_name: str
    stock_market: str

    analyst_reports: Annotated[list[AnalystReport], operator.add]
    completed_roles: Annotated[list[str], operator.add]

    final_report: str
    report_path: str

    audit_extracted: str
    audit_verdict: str
