"""全市场 MACD 金叉 + 稳定区间综合分筛选。

算法在 ``screen`` / ``analyze`` / ``range_scan``；后台任务在 ``service`` / ``range_service``。
本包 ``__init__`` 延迟加载，避免与 ``company.analysis.line.gene`` 循环导入。
"""

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


def __getattr__(name: str):
    if name in ("analyze_macd_stable", "analyze_macd_stable_on_bars"):
        from analysis.macd.analyze import (
            analyze_macd_stable,
            analyze_macd_stable_on_bars,
        )

        return {
            "analyze_macd_stable": analyze_macd_stable,
            "analyze_macd_stable_on_bars": analyze_macd_stable_on_bars,
        }[name]
    if name == "classify_macd_cross":
        from analysis.macd.signals import classify_macd_cross

        return classify_macd_cross
    if name in ("is_eligible_stock", "screen_macd_stable", "slim_row"):
        from analysis.macd.screen import is_eligible_stock, screen_macd_stable, slim_row

        return {
            "is_eligible_stock": is_eligible_stock,
            "screen_macd_stable": screen_macd_stable,
            "slim_row": slim_row,
        }[name]
    if name == "screen_macd_range":
        from analysis.macd.range_scan import screen_macd_range

        return screen_macd_range
    if name == "range_service":
        from analysis.macd.range_service import range_service

        return range_service
    if name == "service":
        from analysis.macd.service import service

        return service
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
