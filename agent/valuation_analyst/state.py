"""估值分析智能体 — 状态。"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ValuationState(TypedDict, total=False):
    company: str
    skip_llm: bool
    force: bool
    data_cutoff_date: str
    stock_code: str
    stock_name: str
    stock_market: str

    pack: dict[str, Any]
    engine: dict[str, Any]
    history_note: str
    fundamentals_note: str
    buffett_note: str
    drivers_note: str
    synthesis_note: str
    report: str
    report_path: str

    sources_used: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
