"""产业链分析智能体 — 状态定义。"""

from __future__ import annotations

from typing import Any, TypedDict


class ChainAnalystState(TypedDict, total=False):
    """产业链分析工作流状态。"""

    company: str

    data_cutoff_date: str
    stock_code: str
    stock_name: str
    stock_market: str
    industry_name: str
    industry_code: str

    data_context: str
    web_context: str
    web_engines: list[str]
    web_search_used: bool
    sources_used: list[str]
    data_available: bool

    chain_map: dict[str, Any]
    chain_map_text: str
    chain_map_ok: bool

    report: str
    report_path: str
