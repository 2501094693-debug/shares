"""AI 相关 HTTP 路由：业务简述、行业竞争、产业链、风险、八看、巴菲特、规则引擎、散户情绪、趋势分析。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from agent.competition_service import (
    get_competition_job,
    list_competition_jobs,
    list_competition_reports,
    read_competition_report,
    start_competition_analysis,
)
from agent.chain_service import (
    get_chain_job,
    list_chain_jobs,
    list_chain_reports,
    read_chain_report,
    start_chain_analysis,
)
from agent.risk_service import (
    get_risk_job,
    list_risk_jobs,
    list_risk_reports,
    read_risk_report,
    start_risk_review,
)
from agent.bazhang_service import (
    get_bazhang_job,
    list_bazhang_jobs,
    list_bazhang_reports,
    read_bazhang_report,
    start_bazhang_analysis,
)
from agent.buffett_service import (
    get_buffett_job,
    list_buffett_jobs,
    list_buffett_reports,
    read_buffett_report,
    start_buffett_analysis,
)
from agent.buffett_rules_service import run_buffett_rules
from agent.retail_service import (
    get_retail_job,
    list_retail_jobs,
    list_retail_reports,
    read_retail_report,
    start_retail_sentiment,
)
from agent.trend_service import (
    get_trend_job,
    list_trend_jobs,
    list_trend_reports,
    read_trend_report,
    start_trend_analysis,
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


@router.post("/api/ai/chain-analysis")
def ai_start_chain_analysis(
    company: str = Query("", description="公司名称或代码"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        job = start_chain_analysis(company)
        return ok(job)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/chain-analysis/jobs")
def ai_list_chain_jobs():
    try:
        return ok(list_chain_jobs())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/chain-analysis/reports")
def ai_list_chain_reports():
    try:
        return ok(list_chain_reports())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/chain-analysis/reports/{filename}")
def ai_get_chain_report(filename: str):
    try:
        content = read_chain_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/chain-analysis/{job_id}")
def ai_get_chain_analysis(job_id: str, full: str = Query("0", description="1=返回完整报告正文")):
    job = get_chain_job(job_id.strip(), include_full_result=full == "1")
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


@router.post("/api/ai/bazhang-analysis")
def ai_start_bazhang_analysis(
    company: str = Query("", description="公司名称或代码"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        job = start_bazhang_analysis(company)
        return ok(job)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/bazhang-analysis/jobs")
def ai_list_bazhang_jobs():
    try:
        return ok(list_bazhang_jobs())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/bazhang-analysis/reports")
def ai_list_bazhang_reports():
    try:
        return ok(list_bazhang_reports())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/bazhang-analysis/reports/{filename}")
def ai_get_bazhang_report(filename: str):
    try:
        content = read_bazhang_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/bazhang-analysis/{job_id}")
def ai_get_bazhang_analysis(job_id: str, full: str = Query("0", description="1=返回完整报告正文")):
    job = get_bazhang_job(job_id.strip(), include_full_result=full == "1")
    if not job:
        return err("任务不存在", 404)
    return ok(job)


@router.post("/api/ai/buffett-analysis")
@router.post("/api/ai/earnings-brief")
@router.post("/api/ai/earnings-review")
def ai_start_buffett_analysis(
    company: str = Query("", description="公司名称或代码"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        job = start_buffett_analysis(company)
        return ok(job)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/buffett-analysis/jobs")
@router.get("/api/ai/earnings-brief/jobs")
@router.get("/api/ai/earnings-review/jobs")
def ai_list_buffett_jobs():
    try:
        return ok(list_buffett_jobs())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/buffett-analysis/reports")
@router.get("/api/ai/earnings-brief/reports")
@router.get("/api/ai/earnings-review/reports")
def ai_list_buffett_reports():
    try:
        return ok(list_buffett_reports())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/buffett-analysis/reports/{filename}")
@router.get("/api/ai/earnings-brief/reports/{filename}")
@router.get("/api/ai/earnings-review/reports/{filename}")
def ai_get_buffett_report(filename: str):
    try:
        content = read_buffett_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/ai/buffett-analysis/{job_id}")
@router.get("/api/ai/earnings-brief/{job_id}")
@router.get("/api/ai/earnings-review/{job_id}")
def ai_get_buffett_analysis(job_id: str, full: str = Query("0", description="1=返回完整报告正文")):
    job = get_buffett_job(job_id.strip(), include_full_result=full == "1")
    if not job:
        return err("任务不存在", 404)
    return ok(job)


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


@router.post("/api/ai/trend-analysis")
def ai_start_trend_analysis(
    company: str = Query("", description="公司名称或代码"),
    day: str = Query("", description="交易日 YYYY-MM-DD，默认最近可用"),
    fund_limit: int = Query(60, description="资金流天数"),
    minute_klt: int = Query(5, description="分钟资金粒度 1|5|15|30|60"),
    min_deal_amount: float = Query(300_000, description="大单最小金额（元）"),
    force: str = Query("0", description="1=强制刷新远端数据"),
):
    company = company.strip()
    if not company:
        return err("缺少参数 company", 400)
    try:
        job = start_trend_analysis(
            company,
            day=day.strip(),
            fund_limit=fund_limit,
            minute_klt=minute_klt,
            min_deal_amount=min_deal_amount,
            force=force in {"1", "true", "yes", "on"},
        )
        return ok(job)
    except ValueError as extra:
        return err(str(extra), 400)
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/trend-analysis/jobs")
def ai_list_trend_jobs():
    try:
        return ok(list_trend_jobs())
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/trend-analysis/reports")
def ai_list_trend_reports():
    try:
        return ok(list_trend_reports())
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/trend-analysis/reports/{filename}")
def ai_get_trend_report(filename: str):
    try:
        content = read_trend_report(filename)
        return ok({"filename": filename, "content": content})
    except FileNotFoundError as extra:
        return err(str(extra), 404)
    except Exception as extra:  # noqa: BLE001
        return err(str(extra), 500)


@router.get("/api/ai/trend-analysis/{job_id}")
def ai_get_trend_analysis(job_id: str, full: str = Query("0", description="1=返回完整报告正文")):
    job = get_trend_job(job_id.strip(), include_full_result=full == "1")
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
