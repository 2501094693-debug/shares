"""张新民「八看」财报解读规则引擎（财报分析）。

八看方法 + 汇总方法，支持按年报 / 半年报 / 一季报 / 三季报口径分析：

    from company.analysis.financialreport import analyze

    pack = analyze("601567", report_type="semi")   # 半年报口径
    pack = analyze("601567", report_type="q3", view="profit")  # 仅三看

报告类型：``annual`` 年报 / ``semi`` 半年报 / ``q1`` 一季报 / ``q3`` 三季报（也接受中文别名）。
"""

from __future__ import annotations

from company.analysis.financialreport._common import (
    REPORT_TYPE_LABELS,
    normalize_report_type,
    report_type_label,
)
from company.analysis.financialreport.engine import analyze, analyze_rows
from company.analysis.financialreport.metrics import compute_bundle
from company.analysis.financialreport.views import (
    VIEW_NAMES,
    build_summary,
    build_views,
)

__all__ = [
    "analyze",
    "analyze_rows",
    "build_views",
    "build_summary",
    "compute_bundle",
    "normalize_report_type",
    "report_type_label",
    "REPORT_TYPE_LABELS",
    "VIEW_NAMES",
]
