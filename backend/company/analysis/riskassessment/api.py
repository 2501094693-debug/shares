"""风险评估 HTTP 路由。

    GET /api/stocks/risk-assessment  巨潮非定期公告七维风险扫描
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Query

from core.api import err, ok

from .report import to_markdown
from .service import RiskAssessmentService

router = APIRouter()

_CODE_RE = re.compile(r"(\d{6})")


def _resolve_code(code: str, company: str) -> str:
    code = str(code or "").strip()
    if code:
        return code
    match = _CODE_RE.search(str(company or ""))
    return match.group(1) if match else ""


def risk_scan_cninfo_only_fetch(code: str) -> dict[str, Any]:
    """七维扫描（CLI / 内部复用）。"""
    return RiskAssessmentService(code).scan()


def risk_scan_cninfo_only_fetch_md(code: str) -> str:
    return RiskAssessmentService(code).scan_markdown()


def risk_scan_cninfo_only_fetch_json(code: str) -> str:
    return RiskAssessmentService(code).scan_json()


@router.get("/api/stocks/risk-assessment")
def stocks_risk_assessment(
    code: str = Query("", description="股票代码，如 000408"),
    company: str = Query("", description="公司查询串（含 6 位代码即可）；与 code 二选一"),
    markdown: str = Query("0", description="1=附带 Markdown 全文"),
):
    """巨潮非定期公告七维排查。

    每个维度返回：检索方式（表格+白话）与按子查询分组的检索结果。
    不调用大模型。
    """
    resolved = _resolve_code(code, company)
    if not resolved:
        return err("缺少参数 code", 400)
    try:
        pack = RiskAssessmentService(resolved).scan()
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)

    stats = pack.get("stats") or {}
    body: dict[str, Any] = {
        "module": "riskassessment",
        "code": pack.get("code") or resolved,
        "name": pack.get("name") or "",
        "source": "巨潮资讯",
        "source_label": "巨潮非定期公告 · 七维检索 · 仅用 fetch_announcements",
        "summary": {
            "dimension_count": stats.get("dimension_count", 0),
            "hit_dimensions": stats.get("hit_dimensions", 0),
            "total_items": stats.get("total_items", 0),
            "total_items_raw": stats.get("total_items_raw", 0),
        },
        "dimensions": pack.get("dimensions") or [],
    }
    if markdown == "1":
        body["markdown"] = to_markdown(pack)
    return ok(body)
