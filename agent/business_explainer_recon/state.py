"""业务解读智能体（复原版）— 状态定义。"""

from __future__ import annotations

from typing import TypedDict


class BusinessExplainerState(TypedDict):
    """公司业务解读工作流状态（冻结版字段）。"""

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
