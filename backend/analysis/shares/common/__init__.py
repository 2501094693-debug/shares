"""三种筛选方法的共用基础设施。"""

from analysis.shares.common.candidates import collect_universe
from analysis.shares.common.config import (
    COMPARE_FIELD_META,
    COMPARE_FIELDS,
    COMPARE_OPS,
    COMPARE_TRENDS,
    DEFAULT_LOOKBACK_DAYS,
    FIELD_META,
    KLINE_LIMIT,
    MAX_LOOKBACK_DAYS,
    RANGE_FIELDS,
)
from analysis.shares.common.days import list_trade_days
from analysis.shares.common.service import service
from analysis.shares.common.view import apply_view

__all__ = [
    "COMPARE_FIELD_META",
    "COMPARE_FIELDS",
    "COMPARE_OPS",
    "COMPARE_TRENDS",
    "DEFAULT_LOOKBACK_DAYS",
    "FIELD_META",
    "KLINE_LIMIT",
    "MAX_LOOKBACK_DAYS",
    "RANGE_FIELDS",
    "apply_view",
    "collect_universe",
    "list_trade_days",
    "service",
]
