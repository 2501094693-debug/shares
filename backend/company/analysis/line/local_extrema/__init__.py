"""个股日线局部极值点（波峰 / 波谷）检测。

把日线图看作离散函数，找出局部极大 / 极小值点（含 prominence 过滤、
距离约束、交替性修正），并输出波段振幅与天数。

日线数据走系统现有 ``company.line.fetcher.fetch_kline``（前复权）。
"""

from __future__ import annotations

from company.analysis.line.local_extrema.service import (
    SERIES_LABELS,
    SERIES_OPTIONS,
    analyze_local_extrema,
    compute_local_extrema,
)

__all__ = [
    "SERIES_LABELS",
    "SERIES_OPTIONS",
    "analyze_local_extrema",
    "compute_local_extrema",
]
