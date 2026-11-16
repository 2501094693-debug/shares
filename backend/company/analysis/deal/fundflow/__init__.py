"""大单资金动向统计（同花顺 HQ 大单四象限 + 定步长分箱）。

取数复用 ``company.statistics.fundflow.tonghuashun.store`` 的当日缓存，
``core`` 做纯计算，``service`` 负责编排，``api`` 暴露 HTTP 路由。

四象限：主动买 / 主动卖 / 被动买 / 被动卖；每个象限给笔数、金额、手数，
并按需附金额分箱（步长 100 万）或手数分箱（步长 100 手），四堆共用同一套
边界，前端可直接叠成堆叠柱状图。
"""

from company.analysis.deal.fundflow.core import (
    AMOUNT_STEP,
    BIN_BY_MODES,
    DEFAULT_BIN_BY,
    EVENT_TYPES,
    LOTS_STEP,
    aggregate_big_deals,
    build_step_edges,
    classify_event,
    normalize_bin_by,
)
from company.analysis.deal.fundflow.service import DEFAULT_MIN_AMOUNT, fetch_big_deal_stats

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