"""散户情绪智能体 — 状态定义。"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class RetailSentimentState(TypedDict, total=False):
    """发声散户情绪工作流状态。"""

    company: str
    days: int
    max_pages: int
    with_replies: bool
    skip_llm: bool
    data_cutoff_date: str
    stock_code: str
    stock_name: str
    stock_market: str

    raw_eastmoney: dict[str, Any]
    raw_tonghuashun: dict[str, Any]
    raw_xueqiu: dict[str, Any]
    platform_scores: dict[str, Any]

    comments: list[dict[str, Any]]
    labels: list[dict[str, Any]]
    metrics: dict[str, Any]
    narrative: str
    report: str
    report_path: str

    sources_used: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
