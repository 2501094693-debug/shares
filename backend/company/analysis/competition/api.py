"""同申万三级行业「八看」横截面比对 HTTP 路由。"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query

from company.analysis.competition.compare import compare_peers
from company.analysis.competition.registry import view_groups
from core.api import err, ok

router = APIRouter()

_CODE_RE = re.compile(r"(\d{6})")


def _resolve_code(code: str, company: str) -> str:
    code = str(code or "").strip()
    if code:
        return code
    match = _CODE_RE.search(str(company or ""))
    return match.group(1) if match else ""


@router.get("/api/stocks/industry-compare")
def stocks_industry_compare(
    code: str = Query("", description="目标股票代码，如 603402"),
    company: str = Query("", description="公司查询串（含 6 位代码即可）；与 code 二选一"),
    industry: str = Query("", description="申万三级行业代码（可选；缺省用目标公司的行业归属）"),
    report_type: str = Query(
        "annual",
        description="报告口径：annual 年报 | semi 半年报 | q1 一季报 | q3 三季报",
    ),
    peers: int = Query(0, ge=0, le=200, description="同行数量上限；0=行业全部可比公司"),
    view: str = Query("", description="只看某一看：strategy|operating|profit|value|cost|quality|risk|outlook|summary；留空返回全部"),
    refresh: str = Query("0", description="1=绕过缓存并强制刷新 F10"),
):
    """张新民「八看」同行业横截面比对：排名、分位、行业基准与目标公司定位。"""
    resolved = _resolve_code(code, company)
    if not resolved and not industry.strip():
        return err("缺少参数 code（或 industry）", 400)
    try:
        data = compare_peers(
            resolved,
            industry_code=industry.strip(),
            report_type=report_type.strip() or "annual",
            peers=peers,
            force=refresh == "1",
            view=view.strip(),
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/industry-compare/meta")
def stocks_industry_compare_meta():
    """八看横截面比对目录：分组 key / 名称 / 指标，供前端渲染导航。"""
    return ok(
        [
            {
                "key": group.key,
                "no": group.no,
                "name": group.name,
                "indicators": [
                    {"key": ind.key, "label": ind.label, "unit": ind.unit, "direction": ind.direction}
                    for ind in group.indicators
                ],
            }
            for group in view_groups()
        ]
    )
