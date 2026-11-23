"""全市场 MACD 金叉 + 稳定区间综合分筛选。

算法在 ``screen`` / ``analyze`` / ``range_scan``；后台任务在 ``service`` / ``range_service``。
"""

from analysis.macd.analyze import analyze_macd_stable, analyze_macd_stable_on_bars
from analysis.macd.range_scan import screen_macd_range
from analysis.macd.range_service import range_service
from analysis.macd.screen import is_eligible_stock, screen_macd_stable, slim_row
from analysis.macd.service import service
from analysis.macd.signals import classify_macd_cross

__all__ = [
    "analyze_macd_stable",
    "analyze_macd_stable_on_bars",
    "classify_macd_cross",
    "is_eligible_stock",
    "range_service",
    "screen_macd_range",
    "screen_macd_stable",
    "service",
    "slim_row",
]
