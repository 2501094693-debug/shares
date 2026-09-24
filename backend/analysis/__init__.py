"""形态筛选。

- ``api``      FastAPI 路由
- ``decline``  阴跌→横盘→涨停
- ``rotation`` 三级行业轮动日历：每天谁涨过、还有谁没涨
- ``shares``   多日日线条件筛选（振幅/实体/涨跌/影线；多日 and/or）
"""

from analysis.decline.screen import screen_decline
from analysis.rotation.screen import screen_rotation
from analysis.shares.pattern import screen_scheme
from analysis.shares.screen import screen_shares

__all__ = [
    "screen_decline",
    "screen_rotation",
    "screen_shares",
    "screen_scheme",
]
