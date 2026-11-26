"""形态筛选。

- ``api``         FastAPI 路由
- ``rotation``    三级行业轮动日历：每天谁涨过、还有谁没涨
- ``macd``        MACD 金叉/即将金叉 + 稳定区间综合分 / 区间回测

子模块请直接 ``from analysis.macd...`` / ``from analysis.rotation...`` 导入，
本包 ``__init__`` 刻意不急载重模块，以免与 ``company.analysis.line.gene`` 循环导入。
"""

__all__ = [
    "screen_macd_range",
    "screen_macd_stable",
    "screen_rotation",
]


def __getattr__(name: str):
    if name == "screen_macd_range":
        from analysis.macd.range_scan import screen_macd_range

        return screen_macd_range
    if name == "screen_macd_stable":
        from analysis.macd.screen import screen_macd_stable

        return screen_macd_stable
    if name == "screen_rotation":
        from analysis.rotation.screen import screen_rotation

        return screen_rotation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
