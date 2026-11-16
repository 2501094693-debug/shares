"""大单资金动向统计：实现位于 ``fundflow`` 子包，此处只做兼容转发。

新代码请直接从 ``company.analysis.deal.fundflow`` 导入。
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