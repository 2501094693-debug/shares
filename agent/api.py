"""AI 相关 HTTP 路由：业务简述、风险、八看、巴菲特规则引擎、散户情绪、估值分析。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from agent.buffett_rules_service import run_buffett_rules
from agent.retail_service import (
    get_retail_job,
    list_retail_jobs,
    list_retail_reports,
    read_retail_report,
    start_retail_sentiment,
)
from agent.valuation_service import (
    get_valuation_job,
    list_valuation_jobs,
    list_valuation_reports,
    read_valuation_report,
    start_valuation_analysis,
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


@router.post("/api/ai/retail-sentiment")
@router.post("/api/ai/sentiment-analysis")
def ai_start_retail_sentiment(
    company: str = Query("", description="公司名称或代码"),
    days: int = Query(3, description="回溯天数"),
    max_pages: int = Query(3, description="每源最多翻页"),
    replies: str = Query("0", description="1=附带热帖回复"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        job = start_retail_sentiment(
            company,
            days=days,
            max_pages=max_pages,
            with_replies=replies in {"1", "true", "yes", "on"},
        )
        return ok(job)
    except ValueError as extra:
        return err(str(extra), 400)
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/retail-sentiment/jobs")
@router.get("/api/ai/sentiment-analysis/jobs")
def ai_list_retail_jobs():
    try:
        return ok(list_retail_jobs())
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/retail-sentiment/reports")
@router.get("/api/ai/sentiment-analysis/reports")
def ai_list_retail_reports():
    try:
        return ok(list_retail_reports())
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/retail-sentiment/reports/{filename}")
@router.get("/api/ai/sentiment-analysis/reports/{filename}")
def ai_get_retail_report(filename: str):
    try:
        content = read_retail_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as extra:
        return err(str(extra), 404)
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/retail-sentiment/{job_id}")
@router.get("/api/ai/sentiment-analysis/{job_id}")
def ai_get_retail_sentiment(job_id: str, full: str = Query("0", description="1=返回完整报告正文")):
    job = get_retail_job(job_id.strip(), include_full_result=full == "1")
    if not job:
        return err("任务不存在", 404)
    return ok(job)


@router.post("/api/ai/valuation-analysis")
def ai_start_valuation_analysis(
    company: str = Query("", description="公司名称或代码"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        return ok(start_valuation_analysis(company))
    except ValueError as extra:
        return err(str(extra), 400)
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/valuation-analysis/jobs")
def ai_list_valuation_jobs():
    try:
        return ok(list_valuation_jobs())
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/valuation-analysis/reports")
def ai_list_valuation_reports():
    try:
        return ok(list_valuation_reports())
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/valuation-analysis/reports/{filename}")
def ai_get_valuation_report(filename: str):
    try:
        content = read_valuation_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as extra:
        return err(str(extra), 404)
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/valuation-analysis/{job_id}")
def ai_get_valuation_analysis(job_id: str, full: str = Query("0", description="1=返回完整报告正文")):
    job = get_valuation_job(job_id.strip(), include_full_result=full == "1")
    if not job:
        return err("任务不存在", 404)
    return ok(job)


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

