"""趋势分析智能体 — 状态。"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class TrendState(TypedDict, total=False):
    """个股趋势分析工作流状态（仅资金 + 分时）。"""

    company: str
    day: str
    fund_limit: int
    minute_klt: int
    min_deal_amount: float
    skip_llm: bool
    force: bool
    data_cutoff_date: str
    stock_code: str
    stock_name: str
    stock_market: str

    pack: dict[str, Any]
    main_force: dict[str, Any]  # 资金动向统计（兼容旧字段名）
    retail: dict[str, Any]  # 分时成交统计（兼容旧字段名）
    verdict: dict[str, Any]
    narrative: str
    report: str
    report_path: str

    sources_used: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
