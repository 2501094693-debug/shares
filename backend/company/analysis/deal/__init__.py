"""成交分析：

- ``fundflow``：大单资金动向统计（四象限 + 分箱）
- ``price_levels``：当日分价表（各价位已成交量）

顶层对 ``fundflow`` 做兼容转发；新代码请直接从子包导入。
"""

from company.analysis.deal.fundflow import (
    AMOUNT_STEP,
    BIN_BY_MODES,
    DEFAULT_BIN_BY,
    DEFAULT_MIN_AMOUNT,
    EVENT_TYPES,
    LOTS_STEP,
    aggregate_big_deals,
    build_step_edges,
    classify_event,
    fetch_big_deal_stats,
    normalize_bin_by,
)

__all__ = [
    "AMOUNT_STEP",
    "BIN_BY_MODES",
    "DEFAULT_BIN_BY",
    "DEFAULT_MIN_AMOUNT",
    "EVENT_TYPES",
    "LOTS_STEP",
    "aggregate_big_deals",
    "build_step_edges",
    "classify_event",
    "fetch_big_deal_stats",
    "normalize_bin_by",
]
