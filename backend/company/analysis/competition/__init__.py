"""同申万三级行业「张新民八看」横截面比对。

    from company.analysis.competition import compare_peers

    pack = compare_peers("603402")                       # 用目标公司的申万三级行业、年报口径
    pack = compare_peers("603402", report_type="semi")   # 半年报口径
    pack = compare_peers("", industry_code="851921")     # 直接指定行业

产出：行业基准、逐指标排名/分位、行业分化度、目标公司定位、一看~八看横截面表与 Markdown。
"""

from __future__ import annotations

from company.analysis.competition.compare import compare_peers
from company.analysis.competition.registry import (
    INDICATORS,
    Indicator,
    view_groups,
    view_name,
)

__all__ = [
    "compare_peers",
    "INDICATORS",
    "Indicator",
    "view_groups",
    "view_name",
]
