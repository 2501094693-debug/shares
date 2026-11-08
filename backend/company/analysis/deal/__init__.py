"""逐笔成交还原：分时成交（总手数 / 笔数）× 资金动向（大单明细）。

管线
----
1. 双手数轴 ``[0, V)``（买/卖两层占用）
2. 按分时窗手数切分区间；笔数为行数预算
3. 大单影响区间 ``I(o)`` → 最小连续区间簇（包含或不相交）
4. 簇内一次性联合落位；无解则被动大→小缩/去，主动小→大只去不缩
5. 窗内展开：小单 ≤ 30 万且尽量均匀；大单尽量撮合

硬约束含 **R12**：匿名侧成交行不得超过 30 万门槛折算整手。
"""

from company.analysis.deal.axis import build_lot_axis
from company.analysis.deal.constants import (
    DEFAULT_AVG_LOTS_PER_TICK,
    DEFAULT_MIN_LOTS,
    DEFAULT_TRADE_THRESHOLD,
    TRADE_MIN_LOTS,
)
from company.analysis.deal.cost import cap_lots, check_rows_cap, window_cost
from company.analysis.deal.emit import emit_window
from company.analysis.deal.influence import (
    AxisIndex,
    InfluenceCluster,
    build_influence_clusters,
    order_influence_range,
    order_touched_windows,
)
from company.analysis.deal.ingest import build_windows, normalize_orders
from company.analysis.deal.pipeline import (
    reconstruct,
    reconstruct_axis,
    reconstruct_windows,
)
from company.analysis.deal.service import (
    format_window_lines,
    run_deal_window_reconstruct,
)
from company.analysis.deal.solver import ClusterSolver, Occupancy, place_joint
from company.analysis.deal.validate import (
    enforce_constraints,
    repair_tape,
    validate_tape,
)

__all__ = [
    "AxisIndex",
    "ClusterSolver",
    "DEFAULT_AVG_LOTS_PER_TICK",
    "DEFAULT_MIN_LOTS",
    "DEFAULT_TRADE_THRESHOLD",
    "InfluenceCluster",
    "Occupancy",
    "TRADE_MIN_LOTS",
    "build_influence_clusters",
    "build_lot_axis",
    "build_windows",
    "cap_lots",
    "check_rows_cap",
    "emit_window",
    "enforce_constraints",
    "format_window_lines",
    "normalize_orders",
    "order_influence_range",
    "order_touched_windows",
    "place_joint",
    "reconstruct",
    "reconstruct_axis",
    "reconstruct_windows",
    "repair_tape",
    "run_deal_window_reconstruct",
    "validate_tape",
    "window_cost",
]
