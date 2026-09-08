"""业务简述智能体 — 状态定义。"""

from __future__ import annotations

from typing import TypedDict


class BusinessExplainerState(TypedDict):
    """公司业务简述工作流状态。"""

    company: str

    data_cutoff_date: str
    stock_code: str
    stock_name: str
    stock_market: str

    data_context: str
    sources_used: list[str]
    data_available: bool

    explanation: str
    brief: str
    report_path: str
