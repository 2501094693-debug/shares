"""个股相对基准日收盘的四价涨跌幅（波动区间 + 统计量）。

输入一只股票 + 起始日期，以「起始日前一交易日」收盘为基准，
返回区间内每日开/高/低/收相对该基准的涨跌幅，以及：

- ``undulate``   四价涨跌幅的波动范围（最低 / 最高）
- ``volatility`` 四价涨跌幅序列的波动范围、均值、标准差与走势
- ``path``       由 S0/U/S1（σ）九格判定上行/下行/冲高回落/探底回升/横盘

日线走系统现有 ``company.line.fetcher.fetch_kline``（前复权）。
"""

from __future__ import annotations

from company.analysis.line.undulate.path import (
    DEFAULT_EPS,
    classify_path,
    path_from_stats,
)
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
    "DEFAULT_EPS",
    "FACTOR_LABELS",
    "FACTORS",
    "analyze_undulate",
    "analyze_volatility",
    "classify_path",
    "compute_stats",
    "compute_undulate",
    "compute_volatility",
    "path_from_stats",
    "summarize_factors",
]
