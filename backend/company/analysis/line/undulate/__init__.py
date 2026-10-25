"""个股相对基准日收盘的四价涨跌幅（波动区间 + 统计量）。

输入一只股票 + 起始日期，以「起始日前一交易日」收盘为基准，
返回区间内每日开/高/低/收相对该基准的涨跌幅，以及：

- ``undulate``   四价涨跌幅的波动范围（最低 / 最高）
- ``volatility`` 四价涨跌幅序列的波动范围、均值、标准差

日线走系统现有 ``company.line.fetcher.fetch_kline``（前复权）。
"""

from __future__ import annotations

from company.analysis.line.undulate.service import (
    FACTOR_LABELS,
    FACTORS,
    analyze_undulate,
    compute_undulate,
)
from company.analysis.line.undulate.stats import compute_stats, summarize_factors
from company.analysis.line.undulate.volatility import (
    analyze_volatility,
    compute_volatility,
)

__all__ = [
    "FACTOR_LABELS",
    "FACTORS",
    "analyze_undulate",
    "analyze_volatility",
    "compute_stats",
    "compute_undulate",
    "compute_volatility",
    "summarize_factors",
]
