"""近一年财报解读智能体 — 状态定义。"""

from __future__ import annotations

from typing import TypedDict


class EarningsReviewerState(TypedDict):
    """指定公司近一年财报解读工作流状态。"""

    company: str

    data_cutoff_date: str
    stock_code: str
    stock_name: str
    stock_market: str

    data_context: str
    sources_used: list[str]
    data_available: bool

    report: str
    report_path: str
