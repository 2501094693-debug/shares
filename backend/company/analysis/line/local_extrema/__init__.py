"""个股日线局部极值点（波峰 / 波谷）检测（支持多层）。

...
"""

from __future__ import annotations

from company.analysis.line.local_extrema.service import (
    SERIES_LABELS,
    SERIES_OPTIONS,
    analyze_alternating_extrema,
    analyze_extrema,
    analyze_extremes,
    analyze_local_extrema,
    analyze_waves,
    compute_alternating_extrema,
    compute_extrema,
    compute_extremes,
    compute_local_extrema,
    compute_waves,
)

# 别名
from company.analysis.line.local_extrema.service import (
    analyze_extrema_layers,
    analyze_hierarchical_extrema,
    analyze_layered_extrema,
    analyze_multilevel_extrema,
    compute_extrema_layers,
    compute_hierarchical_extrema,
    compute_layered_extrema,
    compute_multilevel_extrema,
)

__all__ = [
    "SERIES_LABELS",
    "SERIES_OPTIONS",
    "analyze_alternating_extrema",
    "analyze_extrema_layers",
    "analyze_hierarchical_extrema",
    "analyze_layered_extrema",
    "analyze_local_extrema",
    "analyze_multilevel_extrema",
    "compute_alternating_extrema",
    "compute_extrema_layers",
    "compute_hierarchical_extrema",
    "compute_layered_extrema",
    "compute_local_extrema",
    "compute_multilevel_extrema",
]
