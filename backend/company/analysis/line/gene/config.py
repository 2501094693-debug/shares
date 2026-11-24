"""股性（gene）：MACD 预设与默认参数。

两套默认 MACD 参数与前端 K 线一致：``10,20,7`` / ``12,26,9``。
"""

from __future__ import annotations

from analysis.macd.config import DEFAULT_NEAR_RATIO
from company.analysis.line.MACD.core import (
    DEFAULT_FAST,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
)

# key → (fast, slow, signal)
MACD_PRESETS: dict[str, tuple[int, int, int]] = {
    "10,20,7": (DEFAULT_FAST, DEFAULT_SLOW, DEFAULT_SIGNAL),
    "12,26,9": (12, 26, 9),
}
DEFAULT_PRESET = "10,20,7"
ALLOWED_PRESETS: tuple[str, ...] = tuple(MACD_PRESETS.keys())

DEFAULT_ADJUST = "qfq"
DEFAULT_PRICE = "close"

__all__ = [
    "ALLOWED_PRESETS",
    "DEFAULT_ADJUST",
    "DEFAULT_NEAR_RATIO",
    "DEFAULT_PRESET",
    "DEFAULT_PRICE",
    "MACD_PRESETS",
]
