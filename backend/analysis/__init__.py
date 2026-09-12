"""形态筛选。

- ``api``      FastAPI 路由
- ``decline``  阴跌→横盘→涨停
- ``grind``    阴跌 / 横盘
- ``rotation`` 三级行业轮动日历：每天谁涨过、还有谁没涨
"""

from analysis.decline.screen import screen_decline
from analysis.grind.screen import screen_grind
from analysis.rotation.screen import screen_rotation

__all__ = ["screen_decline", "screen_grind", "screen_rotation"]
