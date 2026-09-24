"""趋势分析任务编排：后台运行 LangGraph，跟踪进度。"""

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
_TREND_REPORT_RE = ("趋势分析",)

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _ensure_ai_deps() -> None:
    try:
        import langgraph  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "缺少 AI 依赖 langgraph（需要 >=1.0）。请在当前 Python 环境执行：\n"
            "  pip install -r requirements.txt\n"
            "或：pip install \"langgraph>=1.0\" langchain langchain-openai python-dotenv"
        ) from None


def _run_trend_job(
    job_id: str,
    company: str,
    *,
    day: str,
    fund_limit: int,
    minute_klt: int,
    min_deal_amount: float,
    force: bool,
    skip_llm: bool,
) -> None:
    job = _jobs[job_id]
    try:
        _ensure_ai_deps()
        from agent.tools.data_fetcher import resolve_company
        from agent.tools.progress import bind, unbind
        from agent.trend_analyst.graph import compile_app

        bind(job, _lock)

        stock = resolve_company(company)
        job["stock"] = stock

        app = compile_app()
        result = app.invoke(
            {
                "company": company,
                "day": day,
                "fund_limit": fund_limit,
                "minute_klt": minute_klt,
                "min_deal_amount": min_deal_amount,
                "force": force,
                "skip_llm": skip_llm,
                "stock_code": stock["code"],
                "stock_name": stock["name"],
                "stock_market": stock["market"],
            }
        )

        report = result.get("report") or ""
        verdict = result.get("verdict") or {}
        job["status"] = "completed"
        job["result"] = {
            "report_path": result.get("report_path", ""),
            "brief": report,
            "report": report,
            "explanation": report,
            "narrative": result.get("narrative") or "",
            "verdict": verdict,
            "main_force": result.get("main_force") or {},
            "retail": result.get("retail") or {},
            "stock_code": result.get("stock_code") or stock["code"],
            "stock_name": result.get("stock_name") or stock["name"],
            "day": result.get("day") or day,
            "sources_used": result.get("sources_used") or [],
            "errors": result.get("errors") or [],
        }
        job["current"] = {
            "node": "",
            "label": "全部完成",
            "phase": "done",
            "phase_label": "已完成",
            "message": "趋势分析已完成",
            "at": _now_iso(),
        }
        job["updated_at"] = _now_iso()
    except Exception as exc:
        logger.exception("趋势分析任务 %s 失败: %s", job_id, exc)
        job["status"] = "failed"
        job["error"] = str(exc)
        job["traceback"] = traceback.format_exc()
        job["updated_at"] = _now_iso()
        try:
            from agent.tools.progress import report as emit_progress

            emit_progress("tr_synth", f"任务失败：{exc}", phase="failed", status="failed", level="error")
        except Exception:
            pass
    finally:
        try:
            from agent.tools.progress import unbind

            unbind()
        except Exception:
            pass


def start_trend_analysis(
    company: str,
    *,
    day: str = "",
    fund_limit: int = 60,
    minute_klt: int = 5,
    min_deal_amount: float = 300_000,
    force: bool = False,
) -> dict[str, Any]:
    company = (company or "").strip()
    if not company:
        raise ValueError("缺少公司名称或代码")

    _ensure_ai_deps()

    from agent.tools.progress import init_trend_analyst_agents

    skip_llm = not bool(os.getenv("OPENAI_API_KEY"))
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "company": company,
        "type": "trend_analysis",
        "status": "running",
        "progress": [],
        "agents": init_trend_analyst_agents(),
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
        target=_run_trend_job,
        args=(job_id, company),
        kwargs={
            "day": (day or "").strip(),
            "fund_limit": max(10, min(int(fund_limit or 60), 120)),
            "minute_klt": minute_klt if minute_klt in {1, 5, 15, 30, 60} else 5,
            "min_deal_amount": max(50_000.0, float(min_deal_amount or 300_000)),
            "force": bool(force),
            "skip_llm": skip_llm,
        },
        daemon=True,
        name=f"ai-trend-{job_id}",
    )
    thread.start()
    return public_trend_job(job)


def list_trend_jobs(*, limit: int = 20) -> list[dict[str, Any]]:
    with _lock:
        jobs = list(_jobs.values())
    running = [job for job in jobs if job.get("status") == "running"]
    others = [job for job in jobs if job.get("status") != "running"]
    running.sort(key=lambda job: job.get("updated_at") or "", reverse=True)
    others.sort(key=lambda job: job.get("updated_at") or "", reverse=True)
    return [
        public_trend_job(job, include_full_result=False)
        for job in (running + others)[: max(1, limit)]
    ]


def get_trend_job(job_id: str, *, include_full_result: bool = True) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        snapshot = job
    return public_trend_job(snapshot, include_full_result=include_full_result)


def public_trend_job(job: dict[str, Any], *, include_full_result: bool = True) -> dict[str, Any]:
    activity_log = job.get("activity_log") or []
    if len(activity_log) > 120:
        activity_log = activity_log[-120:]

    out = {
        "id": job["id"],
        "company": job["company"],
        "type": "trend_analysis",
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
                "verdict": result.get("verdict") or {},
                "day": result.get("day") or "",
                "ready": True,
            }
    if job["status"] == "failed":
        out["error"] = job.get("error", "未知错误")
    return out


def list_trend_reports() -> list[dict[str, Any]]:
    if not _REPORTS_DIR.exists():
        return []
    rows = []
    for path in sorted(_REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not any(tag in path.name for tag in _TREND_REPORT_RE):
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


def read_trend_report(filename: str) -> str:
    safe = Path(filename).name
    path = _REPORTS_DIR / safe
    if not path.exists():
        raise FileNotFoundError(f"报告不存在: {safe}")
    return path.read_text(encoding="utf-8")
