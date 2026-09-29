"""财务估值诊断任务编排：后台线程跑流水线，跟踪进度。"""

from __future__ import annotations

import logging
import os
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AI_DIR = Path(__file__).resolve().parent
_REPORTS_DIR = _AI_DIR / "reports"
_REPORT_TAGS = ("财务估值", "财务数据、盈利能力与估值")

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _run_job(job_id: str, company: str, *, skip_llm: bool) -> None:
    job = _jobs[job_id]
    try:
        from agent.tools.data_fetcher import resolve_company
        from agent.tools.progress import bind, unbind
        from agent.fundamentals_agent.pipeline import run_fundamentals

        bind(job, _lock)
        stock = resolve_company(company)
        job["stock"] = stock
        result = run_fundamentals(company, skip_llm=skip_llm, stock=stock)
        report = result.get("report") or ""
        job["status"] = "completed"
        job["result"] = {
            "report_path": result.get("report_path", ""),
            "brief": report,
            "report": report,
            "explanation": report,
            "stock_code": result.get("stock_code") or stock["code"],
            "stock_name": result.get("stock_name") or stock["name"],
            "stance": result.get("stance") or "",
            "anchor_iv": result.get("anchor_iv"),
            "anchor_mos": result.get("anchor_mos"),
            "dims": result.get("dims") or [],
            "sources_used": result.get("sources_used") or [],
            "errors": result.get("errors") or [],
        }
        job["current"] = {
            "node": "",
            "label": "全部完成",
            "phase": "done",
            "phase_label": "已完成",
            "message": "财务估值诊断已完成",
            "at": _now_iso(),
        }
        job["updated_at"] = _now_iso()
    except Exception as exc:
        logger.exception("财务估值任务 %s 失败: %s", job_id, exc)
        job["status"] = "failed"
        job["error"] = str(exc)
        job["traceback"] = traceback.format_exc()
        job["updated_at"] = _now_iso()
        try:
            from agent.tools.progress import report as emit_progress

            emit_progress("fv_brief", f"任务失败：{exc}", phase="failed", status="failed", level="error")
        except Exception:
            pass
    finally:
        try:
            from agent.tools.progress import unbind

            unbind()
        except Exception:
            pass


def start_fundamentals_analysis(company: str) -> dict[str, Any]:
    company = (company or "").strip()
    if not company:
        raise ValueError("缺少公司名称或代码")

    from agent.tools.progress import init_fundamentals_agents

    skip_llm = not bool(os.getenv("OPENAI_API_KEY"))
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "company": company,
        "type": "fundamentals_analysis",
        "status": "running",
        "progress": [],
        "agents": init_fundamentals_agents(),
        "activity_log": [],
        "current": None,
        "result": None,
        "error": None,
        "stock": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    with _lock:
        _jobs[job_id] = job
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, company),
        kwargs={"skip_llm": skip_llm},
        daemon=True,
        name=f"ai-fundamentals-{job_id}",
    )
    thread.start()
    return public_fundamentals_job(job)


def list_fundamentals_jobs(*, limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        jobs = list(_jobs.values())
    running = [job for job in jobs if job.get("status") == "running"]
    others = [job for job in jobs if job.get("status") != "running"]
    running.sort(key=lambda job: job.get("updated_at") or "", reverse=True)
    others.sort(key=lambda job: job.get("updated_at") or "", reverse=True)
    return [
        public_fundamentals_job(job, include_full_result=False)
        for job in (running + others)[: max(1, limit)]
    ]


def get_fundamentals_job(job_id: str, *, include_full_result: bool = True) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        snapshot = job
    return public_fundamentals_job(snapshot, include_full_result=include_full_result)


def public_fundamentals_job(job: dict[str, Any], *, include_full_result: bool = True) -> dict[str, Any]:
    activity_log = job.get("activity_log") or []
    if len(activity_log) > 120:
        activity_log = activity_log[-120:]
    out = {
        "id": job["id"],
        "company": job["company"],
        "type": "fundamentals_analysis",
        "status": job["status"],
        "agents": job.get("agents", {}),
        "activity_log": activity_log,
        "current": job.get("current"),
        "stock": job.get("stock"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }
    if job["status"] == "completed" and job.get("result"):
        result = job["result"]
        filename = Path(result.get("report_path") or "").name
        if include_full_result:
            out["result"] = {**result, "filename": filename}
        else:
            out["result"] = {
                "report_path": result.get("report_path", ""),
                "filename": filename,
                "stock_code": result.get("stock_code", ""),
                "stock_name": result.get("stock_name", ""),
                "stance": result.get("stance", ""),
                "anchor_iv": result.get("anchor_iv"),
                "anchor_mos": result.get("anchor_mos"),
                "ready": True,
            }
    if job["status"] == "failed":
        out["error"] = job.get("error", "未知错误")
    return out


def list_fundamentals_reports() -> list[dict[str, Any]]:
    if not _REPORTS_DIR.exists():
        return []
    rows = []
    for path in sorted(_REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not any(tag in path.name for tag in _REPORT_TAGS):
            continue
        stat = path.stat()
        rows.append(
            {
                "filename": path.name,
                "path": str(path),
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return rows


def read_fundamentals_report(filename: str) -> str:
    safe = Path(filename).name
    path = _REPORTS_DIR / safe
    if not path.exists():
        raise FileNotFoundError(f"报告不存在: {safe}")
    return path.read_text(encoding="utf-8")
