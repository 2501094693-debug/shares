"""阴跌 / 横盘形态筛选。

从最近一根日 K 向前识别仍在持续的阴跌或横盘，只给软评分，无硬门槛。
"""

from analysis.grind.screen import analyze_one, screen_grind
from analysis.grind.service import service

__all__ = ["analyze_one", "screen_grind", "service"]
