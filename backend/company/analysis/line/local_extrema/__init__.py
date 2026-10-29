"""个股日线局部极值点（波峰 / 波谷）检测。

把日线图看作离散函数，用**相邻比较**找出极值点：

- 大于等于左右两个相邻交易日 → 波峰；
- 小于等于左右两个相邻交易日 → 波谷。

运行前先合并连续相同值（平台只取一个点），因此 `1,2,2,2,1` 只产生一个波峰。

并记录每个极值点向左右各延续多少个交易日（left_span / right_span），
用于描述该极值形态覆盖的天数宽度。

提供两种输出：

- ``compute_local_extrema`` / ``analyze_local_extrema``：
  按交易日从远到近排列的单一峰谷序列（extrema）；
- ``compute_alternating_extrema`` / ``analyze_alternating_extrema``：
  峰谷序列（extrema），合并连续出现的同类型极值（峰取最高、谷取最低），
  不做过滤。

日线数据走系统现有 ``company.line.fetcher.fetch_kline``（前复权）。
"""

from __future__ import annotations

from company.analysis.line.local_extrema.service import (
    SERIES_LABELS,
    SERIES_OPTIONS,
    analyze_alternating_extrema,
    analyze_local_extrema,
    compute_alternating_extrema,
    compute_local_extrema,
)

__all__ = [
    "SERIES_LABELS",
    "SERIES_OPTIONS",
    "analyze_alternating_extrema",
    "analyze_local_extrema",
    "compute_alternating_extrema",
    "compute_local_extrema",
]
