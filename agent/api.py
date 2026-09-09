"""AI 相关 HTTP 路由：业务简述、财报解读、行业竞争分析、风险与管理层评估。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from agent.competition_service import (
    get_competition_job,
    list_competition_jobs,
    list_competition_reports,
    read_competition_report,
    start_competition_analysis,
)
from agent.risk_service import (
    get_risk_job,
    list_risk_jobs,
    list_risk_reports,
    read_risk_report,
    start_risk_review,
)
from agent.earnings_service import (
    get_earnings_job,
    list_earnings_jobs,
    list_earnings_reports,
    read_earnings_report,
    start_earnings_review,
)
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


@router.post("/api/ai/earnings-brief")
@router.post("/api/ai/earnings-review")
def ai_start_earnings_review(
    company: str = Query("", description="公司名称或代码"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        job = start_earnings_review(company)
        return ok(job)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/earnings-brief/jobs")
@router.get("/api/ai/earnings-review/jobs")
def ai_list_earnings_jobs():
    try:
        return ok(list_earnings_jobs())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/earnings-brief/reports")
@router.get("/api/ai/earnings-review/reports")
def ai_list_earnings_reports():
    try:
        return ok(list_earnings_reports())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/earnings-brief/reports/{filename}")
@router.get("/api/ai/earnings-review/reports/{filename}")
def ai_get_earnings_report(filename: str):
    try:
        content = read_earnings_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/earnings-brief/{job_id}")
@router.get("/api/ai/earnings-review/{job_id}")
def ai_get_earnings_review(job_id: str, full: str = Query("0", description="1=返回完整简述正文")):
    job = get_earnings_job(job_id.strip(), include_full_result=full == "1")
    if not job:
        return err("任务不存在", 404)
    return ok(job)


@router.post("/api/ai/competition-analysis")
def ai_start_competition_analysis(
    company: str = Query("", description="公司名称或代码"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        job = start_competition_analysis(company)
        return ok(job)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/competition-analysis/jobs")
def ai_list_competition_jobs():
    try:
        return ok(list_competition_jobs())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/competition-analysis/reports")
def ai_list_competition_reports():
    try:
        return ok(list_competition_reports())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/competition-analysis/reports/{filename}")
def ai_get_competition_report(filename: str):
    try:
        content = read_competition_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/competition-analysis/{job_id}")
def ai_get_competition_analysis(job_id: str, full: str = Query("0", description="1=返回完整报告正文")):
    job = get_competition_job(job_id.strip(), include_full_result=full == "1")
    if not job:
        return err("任务不存在", 404)
    return ok(job)


@router.post("/api/ai/risk-review")
def ai_start_risk_review(
    company: str = Query("", description="公司名称或代码"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        job = start_risk_review(company)
        return ok(job)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/risk-review/jobs")
def ai_list_risk_jobs():
    try:
        return ok(list_risk_jobs())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/risk-review/reports")
def ai_list_risk_reports():
    try:
        return ok(list_risk_reports())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/risk-review/reports/{filename}")
def ai_get_risk_report(filename: str):
    try:
        content = read_risk_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/risk-review/{job_id}")
def ai_get_risk_review(job_id: str, full: str = Query("0", description="1=返回完整报告正文")):
    job = get_risk_job(job_id.strip(), include_full_result=full == "1")
    if not job:
        return err("任务不存在", 404)
    return ok(job)
