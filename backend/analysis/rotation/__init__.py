"""申万三级行业：每天谁轮到了，还有谁没涨过。"""

from analysis.rotation.calendar import screen_rotation
from analysis.rotation.service import service

__all__ = ["screen_rotation", "service"]
