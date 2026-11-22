"""全市场 MACD 金叉 + 稳定区间综合分筛选。

算法在 ``screen`` / ``analyze``；后台任务在 ``service``。
"""

from analysis.macd.analyze import analyze_macd_stable
from analysis.macd.screen import is_eligible_stock, screen_macd_stable, slim_row
from analysis.macd.service import service
from analysis.macd.signals import classify_macd_cross

__all__ = [
    "analyze_macd_stable",
    "classify_macd_cross",
    "is_eligible_stock",
    "screen_macd_stable",
    "service",
    "slim_row",
]
