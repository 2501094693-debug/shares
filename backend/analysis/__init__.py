"""形态筛选。

- ``api``     FastAPI 路由（``GET /api/screen/decline``、``GET /api/screen/grind``）
- ``decline`` 阴跌→横盘→涨停：算法、评分、后台任务
- ``grind``  阴跌 / 横盘：全市场软评分
"""

from analysis.decline.screen import screen_decline
from analysis.grind.screen import screen_grind

__all__ = ["screen_decline", "screen_grind"]
