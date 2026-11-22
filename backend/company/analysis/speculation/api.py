"""炒作分析 HTTP 路由。

    GET /api/stocks/speculation  筹码门槛 + 十大股东/流通股东 + 剔重基金 + 三源热度
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query

from company.analysis.speculation.service import build_speculation
from core.api import err, ok

router = APIRouter()

_CODE_RE = re.compile(r"(\d{6})")


def _resolve_code(code: str, company: str) -> str:
    code = str(code or "").strip()
    if code:
        return code
    match = _CODE_RE.search(str(company or ""))
    return match.group(1) if match else ""


@router.get("/api/stocks/speculation")
def stocks_speculation(
    code: str = Query("", description="股票代码，如 600519"),
    company: str = Query("", description="公司查询串（含 6 位代码即可）；与 code 二选一"),
    holders_date: str = Query("", description="十大股东报告期 YYYY-MM-DD；空=最新"),
    funds_date: str = Query("", description="基金持股报告期；空则跟 holders_date / 最新"),
    heat: str = Query("1", description="1=含三源热度；0=仅筹码与股东"),
):
    """炒作分析：自由流通坐庄门槛、前十大/流通股东、剔重基金、东财十日+同花顺/雪球今日热度。"""
    resolved = _resolve_code(code, company)
    if not resolved:
        return err("缺少参数 code", 400)
    try:
        data = build_speculation(
            resolved,
            holders_date=holders_date.strip() or None,
            funds_date=funds_date.strip() or None,
            include_heat=heat not in {"0", "false", "no", "off"},
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
