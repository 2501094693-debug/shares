"""兼容门面：联合落位 + 窗内展开。"""

from company.analysis.deal.emit import emit_window
from company.analysis.deal.solver import (
    ClusterSolver,
    Occupancy,
    SolveResult,
    place_joint,
)

__all__ = [
    "ClusterSolver",
    "Occupancy",
    "SolveResult",
    "emit_window",
    "place_joint",
]
