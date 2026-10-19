"""同花顺部分：F10「经营分析」接入（唯一数据源）。

对外只暴露一个统一适配器 :data:`SOURCE`，使 ``core.engine``
能把它当作标准插件使用。
"""

from __future__ import annotations

from company.analysis.businessoverview.core.source import Source
from company.analysis.businessoverview.tonghuashun.fetcher import (
    ALL_ANALYSIS,
    ANALYSIS_DIM,
    HISTORY_API,
    PRODUCT_INDEX_API,
    TYPE_PRIORITY,
    fetch_business_intro,
    fetch_business_review,
    fetch_operate_all_dimensions,
    fetch_operate_analysis,
    fetch_operate_dimensions,
    fetch_operate_page_text,
    fetch_operate_segments,
    fetch_operate_text_blocks,
    fetch_periods,
    normalize_analysis_type,
    operate_page_url,
)

def _segments(code, latest_n=1, dimension="", date=""):
    return fetch_operate_segments(
        code, latest_n=latest_n, analysis_type=dimension, date=date
    )


def _fetch_all(code, latest_n=1, analysis_type=""):
    return fetch_operate_analysis(
        code, latest_n=latest_n, analysis_type=analysis_type
    )


SOURCE = Source(
    key="tonghuashun",
    label="同花顺 F10 经营分析",
    page_url="https://basic.10jqka.com.cn/{code}/operate.html",
    api=PRODUCT_INDEX_API,
    dim_labels=dict(
        product=ANALYSIS_DIM["product"],
        industry=ANALYSIS_DIM["industry"],
        area=ANALYSIS_DIM["area"],
    ),
    dim_priority=TYPE_PRIORITY,
    normalize_dim=normalize_analysis_type,
    fetch_segments=_segments,
    fetch_all=_fetch_all,
    fetch_periods=fetch_periods,
)

__all__ = [
    "SOURCE",
    "Source",
    "PRODUCT_INDEX_API",
    "HISTORY_API",
    "ALL_ANALYSIS",
    "ANALYSIS_DIM",
    "TYPE_PRIORITY",
    "normalize_analysis_type",
    "operate_page_url",
    "fetch_periods",
    "fetch_operate_segments",
    "fetch_operate_all_dimensions",
    "fetch_operate_dimensions",
    "fetch_operate_text_blocks",
    "fetch_business_intro",
    "fetch_business_review",
    "fetch_operate_page_text",
    "fetch_operate_analysis",
]
