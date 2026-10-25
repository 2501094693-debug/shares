"""股票 vs 指数日线四项对比。

对比口径（相对各自前收）：
- open  开盘涨跌幅
- high  最大涨幅
- low   最大跌幅
- close 收盘涨跌幅

每日输出方向（同涨 / 同跌 / 股涨指跌 / 股跌指涨）与股−指差值。
数据源：个股 ``company.line.fetcher.fetch_kline``；
指数 ``exponent.fetch_kline``（同花顺优先，东财 / 缓存 / 腾讯兜底）。
"""

from __future__ import annotations

from company.analysis.line.compare.service import (
    available_indices,
    compare_stock_vs_index,
    compare_stock_vs_indices,
)

__all__ = [
    "available_indices",
    "compare_stock_vs_index",
    "compare_stock_vs_indices",
]
