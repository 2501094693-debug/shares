"""阴跌→横盘→涨停形态筛选。

算法在 ``screen``；后台任务在 ``service``。
"""

from analysis.decline.screen import screen_decline
from analysis.decline.service import service

__all__ = ["screen_decline", "service"]
