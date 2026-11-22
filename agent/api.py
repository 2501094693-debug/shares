"""AI 相关 HTTP 路由：业务简述、巴菲特规则引擎。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from agent.buffett_rules_service import run_buffett_rules
from agent.service import get_brief_job, list_brief_jobs, list_reports, read_report, start_business_brief
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


@router.get("/api/ai/business-brief/jobs")
def ai_list_brief_jobs():
    try:
        return ok(list_brief_jobs())
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


@router.get("/api/ai/buffett-rules")
def ai_buffett_rules(
    company: str = Query("", description="公司名称或代码"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        return ok(run_buffett_rules(company))
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
