"""兼容门面：常量 / 摄入 / 重建入口。

旧的按窗求解器已删除；``reconstruct_windows`` 永远走双轴联合落位。
"""

from __future__ import annotations

from company.analysis.deal.constants import (
    DEFAULT_AVG_LOTS_PER_TICK,
    DEFAULT_MIN_LOTS,
    DEFAULT_TRADE_THRESHOLD,
    SHARES_PER_LOT,
    TRADE_MIN_LOTS,
)
from company.analysis.deal.emit import emit_window
from company.analysis.deal.ingest import (
    build_windows,
    filter_auction_ticks,
    normalize_orders,
)
from company.analysis.deal.pipeline import (
    reconstruct,
    reconstruct_axis,
    reconstruct_windows,
)
from company.analysis.deal.util import (
    _OrderIds,
    _align_window_vwap,
    _cap_lots_int,
    _deadline_index,
    _deadline_indices,
    _f,
    _lots_int,
    _min_lots_floor,
    _order_fill_stamp,
    _shift_stamp,
    _split,
    _stamp_key,
)

__all__ = [
    "DEFAULT_AVG_LOTS_PER_TICK",
    "DEFAULT_MIN_LOTS",
    "DEFAULT_TRADE_THRESHOLD",
    "SHARES_PER_LOT",
    "TRADE_MIN_LOTS",
    "_OrderIds",
    "_align_window_vwap",
    "_cap_lots_int",
    "_deadline_index",
    "_deadline_indices",
    "_f",
    "_lots_int",
    "_min_lots_floor",
    "_order_fill_stamp",
    "_shift_stamp",
    "_split",
    "_stamp_key",
    "build_windows",
    "emit_window",
    "filter_auction_ticks",
    "normalize_orders",
    "reconstruct",
    "reconstruct_axis",
    "reconstruct_windows",
]
