"""手数轴：给分时窗挂上 ``[L, R)`` 坐标。"""

from __future__ import annotations

from typing import Any

from company.analysis.deal.influence import (
    AxisIndex,
    InfluenceCluster,
    build_influence_clusters,
    order_influence_range,
    order_touched_windows,
)
from company.analysis.deal.util import _lots_int


def build_lot_axis(
    windows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """给每个分时窗挂上 ``[L, R)`` 手数轴坐标，返回 ``(axis_windows, V)``。"""
    axis: list[dict[str, Any]] = []
    cursor = 0
    for index, window in enumerate(windows):
        lots = _lots_int(window.get("lots"))
        left = cursor
        right = cursor + lots
        row = dict(window)
        row["index"] = index
        row["L"] = left
        row["R"] = right
        row["prev_time"] = str(windows[index - 1]["time"]) if index > 0 else ""
        axis.append(row)
        cursor = right
    return axis, cursor


__all__ = [
    "AxisIndex",
    "InfluenceCluster",
    "build_influence_clusters",
    "build_lot_axis",
    "order_influence_range",
    "order_touched_windows",
]
