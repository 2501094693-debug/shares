"""形态筛选。

- ``api``         FastAPI 路由
- ``rotation``    三级行业轮动日历：每天谁涨过、还有谁没涨
- ``macd``        MACD 金叉/即将金叉 + 稳定区间综合分 / 区间回测
"""

from analysis.macd.range_scan import screen_macd_range
from analysis.macd.screen import screen_macd_stable
from analysis.rotation.screen import screen_rotation

__all__ = [
    "screen_macd_range",
    "screen_macd_stable",
    "screen_rotation",
]
