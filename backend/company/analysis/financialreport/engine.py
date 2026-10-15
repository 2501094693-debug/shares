"""张新民「八看」规则引擎：数据获取 + 编排。

对外入口：
- ``analyze(code, report_type)``：拉最新全量定期报告后按所选口径运行八看 + 汇总；
- ``analyze_rows(merged, report_type)``：直接对既有的 F10 合并行运行（便于测试/复用）。
"""

from __future__ import annotations

from typing import Any

from company.analysis.financialreport._common import (
    period_label,
    report_type_label,
    select_series,
    normalize_report_type,
)
from company.analysis.financialreport.metrics import compute_bundle
from company.analysis.financialreport.views import build_summary, build_views

SERIES_LIMIT = 8


def _ytd_flag(series: list[dict[str, Any]], report_type: str) -> str | None:
    if not series or report_type == "annual":
        return None
    label = report_type_label(report_type)
    return (
        f"本次依据{label}口径：利润表/现金流量表为累计数（半年报=上半年、三季报=前三季度），"
        f"不可与年报直接横比；周转天数按累计数估算会偏高"
    )


def analyze_rows(
    merged: list[dict[str, Any]] | None,
    report_type: str = "annual",
    *,
    code: str = "",
    name: str = "",
    limit: int = SERIES_LIMIT,
) -> dict[str, Any]:
    """对 F10 合并行按所选报告类型运行八看与汇总。"""
    rt = normalize_report_type(report_type)
    series = select_series(merged, rt, limit=limit)

    if not series:
        return {
            "code": code,
            "name": name,
            "report_type": rt,
            "report_type_label": report_type_label(rt),
            "data_available": False,
            "latest_period": "",
            "period_kind": "",
            "coverage": "",
            "strategy_type": "未知",
            "flags": [],
            "views": [],
            "summary": None,
            "text": f"（未获取到{report_type_label(rt)}口径的定期报告数据）",
        }

    bundle = compute_bundle(series)
    flags = list(bundle.get("flags") or [])
    ytd = _ytd_flag(series, rt)
    if ytd:
        flags.insert(0, ytd)
    bundle["flags"] = flags

    coverage = f"同口径{len(series)}期{report_type_label(rt)}"
    views = build_views(series, bundle)
    summary = build_summary(series, bundle, coverage=coverage)

    text_parts = [f"# 张新民「八看」·{report_type_label(rt)}口径", ""]
    for view in views:
        text_parts.append(f"## {view['name']}")
        text_parts.append(view["text"])
        text_parts.append("")
    text_parts.append(f"## {summary['name']}")
    text_parts.append(summary["text"])

    return {
        "code": code,
        "name": name,
        "report_type": rt,
        "report_type_label": report_type_label(rt),
        "data_available": True,
        "latest_period": bundle.get("latest_period") or period_label(series[0]),
        "period_kind": bundle.get("period_kind") or "",
        "coverage": coverage,
        "strategy_type": (bundle.get("strategy") or {}).get("strategy_type", "未知"),
        "ytd": rt != "annual",
        "flags": flags,
        "metrics": {
            "assets": bundle.get("assets"),
            "liabilities": bundle.get("liabilities"),
            "profit": bundle.get("profit"),
            "cash": bundle.get("cash"),
            "competitiveness": bundle.get("competitiveness"),
            "strategy": bundle.get("strategy"),
        },
        "views": views,
        "summary": summary,
        "text": "\n".join(text_parts),
    }


def analyze(
    code: str,
    report_type: str = "annual",
    *,
    name: str = "",
    limit: int = 60,
    force: bool = False,
    view: str = "",
) -> dict[str, Any]:
    """拉取东财 F10 全量定期报告后运行八看。

    ``report_type``：``annual`` 年报 / ``semi`` 半年报 / ``q1`` 一季报 / ``q3`` 三季报。
    ``view``：留空返回全部八看 + 汇总；否则只返回指定的一看（``strategy`` 等）。
    """
    from company.news.financialreport.fetcher import get_financial_report

    pack = get_financial_report(code, scope="all", limit=limit, force=force)
    merged = pack.get("merged") or []
    result = analyze_rows(merged, report_type, code=code, name=name)
    result["source"] = pack.get("source") or ""

    key = str(view or "").strip().lower()
    if key and result.get("views"):
        from company.analysis.financialreport.views import VIEW_NAMES

        if key in VIEW_NAMES:
            result["selected_view"] = next((v for v in result["views"] if v["key"] == key), None)
        elif key in {"summary", "diagnosis", "汇总", "综合诊断"}:
            result["selected_view"] = result.get("summary")
        else:
            valid = ",".join([*VIEW_NAMES, "summary"])
            raise ValueError(f"view 须为 {valid}")
    return result
