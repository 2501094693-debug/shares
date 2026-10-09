"""定期报告 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response

from company.news.periodicreport.fetcher import get_periodic_report
from company.news.periodicreport.pdf import pdf_meta, render_pdf_page
from core.api import err, ok

router = APIRouter()


@router.get("/api/stocks/periodic-report")
def stocks_periodic_report(
    code: str = Query("", description="股票代码，如 600519"),
    period: str = Query(
        "",
        description="报告期，如 2025-annual / 2025年报；空则 selected 为最新一期",
    ),
    days: int = Query(1825, ge=1, le=20000, description="回溯天数，默认约 5 年"),
    refresh: str = Query("0", description="1=跳过缓存"),
):
    """返回报告期列表 + 最新一期；可用 period 指定当前选中期。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        return ok(
            get_periodic_report(
                code,
                days=days,
                period=period.strip(),
                force=refresh == "1",
            )
        )
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/periodic-report/pdf/meta")
def stocks_periodic_report_pdf_meta(
    url: str = Query(..., description="监管披露 PDF 绝对地址"),
    refresh: str = Query("0"),
):
    """PDF 页数与目录（正文目录页优先，其次书签），供前端按页展示与跳转。"""
    try:
        return ok(pdf_meta(url.strip(), force=refresh == "1"))
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/periodic-report/pdf/page")
def stocks_periodic_report_pdf_page(
    url: str = Query(..., description="监管披露 PDF 绝对地址"),
    page: int = Query(1, ge=1, le=500, description="页码，从 1 开始"),
    refresh: str = Query("0"),
):
    """渲染单页为 PNG（最高清晰度），前端按页滚动阅读。"""
    try:
        data = render_pdf_page(url.strip(), page, force=refresh == "1")
        return Response(
            content=data,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=1800",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
