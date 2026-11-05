"""日线段划分（section）：最小段 → 同向合并 → 涨跌交替归横盘 → 缓涨/缓跌。"""

from __future__ import annotations

from company.analysis.line.section.core import (
    DIR_DOWN,
    DIR_FLAT,
    DIR_LABEL,
    DIR_SLOW_DOWN,
    DIR_SLOW_UP,
    DIR_UP,
    SERIES_LABELS,
    SERIES_OPTIONS,
    build_minimal_segments,
    compute_sections,
)
from company.analysis.line.section.service import analyze_sections

__all__ = [
    "DIR_DOWN",
    "DIR_FLAT",
    "DIR_LABEL",
    "DIR_SLOW_DOWN",
    "DIR_SLOW_UP",
    "DIR_UP",
    "SERIES_LABELS",
    "SERIES_OPTIONS",
    "analyze_sections",
    "build_minimal_segments",
    "compute_sections",
]
