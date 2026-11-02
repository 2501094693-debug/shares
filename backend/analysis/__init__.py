"""形态筛选。

- ``api``      FastAPI 路由
- ``decline``  阴跌→横盘→涨停
- ``rotation`` 三级行业轮动日历：每天谁涨过、还有谁没涨
- ``evaluate`` 全市场区间评估（强弱 / 偏离 / 低点分）
"""

from analysis.decline.screen import screen_decline
from analysis.evaluate.screen import screen_evaluate
from analysis.rotation.screen import screen_rotation

__all__ = [
    "screen_decline",
    "screen_evaluate",
    "screen_rotation",
]
