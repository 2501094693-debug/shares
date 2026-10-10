"""个股 / 指数 / 板块 K 线与逐笔（东财 / 腾讯 / 同花顺）。

布局（按数据源分子包，共用层放顶层）：

- ``session``：A 股交易时段（上海时区），缓存归属交易日都用它。
- ``fetcher``：统一入口 + 内存/TTL/磁盘缓存（``fetch_kline`` / ``fetch_ticks``）。
- ``eastmoney``：东财 K 线（``kline``）+ 实时逐笔（``ticks``）。
- ``tencent``：腾讯 K 线（``kline``）+ 实时逐笔（``ticks``）。
- ``tonghuashun``：同花顺 HQ 分时（``hq_ticks``）+ 落盘（``store``），统一由 ``fetcher`` 调度。

顶层 ``eastmoney_kline`` 等四个文件是兼容垫片，旧引用仍可用，
新代码请从子包导入。
"""

from company.line.eastmoney.kline import (
    ALL_PERIODS,
    BAR_PERIODS,
    DEFAULT_PERIODS,
    MINUTE_PERIODS,
    PERIOD_KLT,
    fetch_line,
    fetch_lines,
    resolve_secid,
)
from company.line.eastmoney.ticks import fetch_ticks as fetch_eastmoney_ticks
from company.line.fetcher import fetch_kline, fetch_ticks
from company.line.tencent.kline import (
    fetch_line as fetch_tencent_line,
    fetch_lines as fetch_tencent_lines,
    resolve_symbol as resolve_tencent_symbol,
)
from company.line.tencent.ticks import fetch_ticks as fetch_tencent_ticks

__all__ = [
    "ALL_PERIODS",
    "BAR_PERIODS",
    "DEFAULT_PERIODS",
    "MINUTE_PERIODS",
    "PERIOD_KLT",
    "fetch_eastmoney_ticks",
    "fetch_kline",
    "fetch_line",
    "fetch_lines",
    "fetch_tencent_line",
    "fetch_tencent_lines",
    "fetch_tencent_ticks",
    "fetch_ticks",
    "resolve_secid",
    "resolve_tencent_symbol",
]
