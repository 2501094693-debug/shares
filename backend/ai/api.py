"""AI 相关 HTTP 路由：业务简述、投研团队。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ai.research_service import (
    get_research_job,
    list_research_reports,
    read_research_report,
    start_investment_research,
)
from ai.service import get_brief_job, list_reports, read_report, start_business_brief
from core.api import err, ok

router = APIRouter()


@router.post("/api/ai/business-brief")
def ai_start_business_brief(
    company: str = Query("", description="公司名称或代码"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        job = start_business_brief(company)
        return ok(job)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/business-brief/{job_id}")
def ai_get_business_brief(job_id: str, full: str = Query("0", description="1=返回完整简述正文")):
    job = get_brief_job(job_id.strip(), include_full_result=full == "1")
    if not job:
        return err("任务不存在", 404)
    return ok(job)


@router.get("/api/ai/reports")
def ai_list_reports():
    try:
        return ok(list_reports())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/reports/{filename}")
def ai_get_report(filename: str):
    try:
        content = read_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/ai/research")
def ai_start_research(
    company: str = Query("", description="公司名称或代码"),
    request: str = Query("", description="额外研究要求"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        job = start_investment_research(company, request.strip())
        return ok(job)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/research/reports")
def ai_list_research_reports():
    try:
        return ok(list_research_reports())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/research/reports/{filename}")
def ai_get_research_report(filename: str):
    try:
        content = read_research_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/research/{job_id}")
def ai_get_research(job_id: str, full: str = Query("0", description="1=返回完整报告正文")):
    job = get_research_job(job_id.strip(), include_full_result=full == "1")
    if not job:
        return err("任务不存在", 404)
    return ok(job)
