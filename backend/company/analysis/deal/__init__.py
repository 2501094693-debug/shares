"""逐笔成交还原：分时成交（总手数 / 笔数 / 主动买卖）× 资金动向（大单明细）。

- ``window``：3 秒窗口级约束求解，求出一个满足全部约束的可行解并标注订单
- ``sources``：两路数据源适配，均复用系统现有实现
- ``service``：编排主入口 ``run_deal_window_reconstruct``

注意：单笔下限默认 0 手（``DEFAULT_MIN_LOTS``）。输出只允许整手
（0 / 1 / 2 …），禁止小数手；``笔数 > 手数`` 时用 0 手占位保笔数。
"""

from company.analysis.deal.service import (
    format_window_lines,
    run_deal_window_reconstruct,
)
from company.analysis.deal.window import (
    DEFAULT_AVG_LOTS_PER_TICK,
    DEFAULT_MIN_LOTS,
    DEFAULT_TRADE_THRESHOLD,
    TRADE_MIN_LOTS,
    build_windows,
    emit_window,
    normalize_orders,
    place_orders,
    plan_window,
    plan_windows,
    reconstruct_windows,
)

__all__ = [
    "DEFAULT_AVG_LOTS_PER_TICK",
    "DEFAULT_MIN_LOTS",
    "DEFAULT_TRADE_THRESHOLD",
    "TRADE_MIN_LOTS",
    "build_windows",
    "emit_window",
    "format_window_lines",
    "normalize_orders",
    "place_orders",
    "plan_window",
    "plan_windows",
    "reconstruct_windows",
    "run_deal_window_reconstruct",
]
