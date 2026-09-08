"""投研团队任务编排：后台运行 agent LangGraph，跟踪进度。"""

from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_AGENT_DIR = _ROOT / "agent"
_REPORTS_DIR = _AGENT_DIR / "reports"
_RESEARCH_REPORT_RE = ("投资研究报告",)

if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))
if str(_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_ROOT / "backend"))

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _ensure_agent_deps() -> None:
    try:
        import langgraph  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "缺少 AI 依赖 langgraph（需要 >=1.0）。请在当前 Python 环境执行：\n"
            "  pip install -r agent/requirements.txt"
        ) from None


def _run_research_job(job_id: str, company: str, user_request: str) -> None:
    job = _jobs[job_id]
    try:
        _ensure_agent_deps()
        from graph import compile_app
        from tools.data_fetcher import resolve_company
        from tools.progress import bind, unbind

        bind(job, _lock)

        stock = resolve_company(company)
        job["stock"] = stock

        app = compile_app()
        initial_state = {
            "company": company,
            "user_request": user_request or f"对{company}进行团队化投资研究分析",
            "stock_code": stock["code"],
            "stock_name": stock["name"],
            "stock_market": stock["market"],
            "analyst_reports": [],
            "completed_roles": [],
        }

        result: dict[str, Any] = {}
        for event in app.stream(initial_state, stream_mode="updates"):
            for _node, update in event.items():
                result.update(update)

        job["status"] = "completed"
        job["result"] = {
            "report_path": result.get("report_path", ""),
            "final_report": result.get("final_report", ""),
            "info_richness": result.get("info_richness", ""),
            "info_richness_rationale": result.get("info_richness_rationale", ""),
            "stock_code": result.get("stock_code") or stock["code"],
            "stock_name": result.get("stock_name") or stock["name"],
            "audit_extracted": result.get("audit_extracted", ""),
            "analyst_reports": [
                {
                    "role": r.get("role"),
                    "role_cn": r.get("role_cn"),
                    "framework": r.get("framework"),
                    "score": r.get("score"),
                    "confidence_note": r.get("confidence_note"),
                }
                for r in (result.get("analyst_reports") or [])
            ],
        }
        job["current"] = {
            "node": "",
            "label": "全部完成",
            "phase": "done",
            "phase_label": "已完成",
            "message": "投研报告已生成",
            "at": _now_iso(),
        }
        job["updated_at"] = _now_iso()
    except Exception as exc:
        logger.exception("投研任务 %s 失败: %s", job_id, exc)
        job["status"] = "failed"
        job["error"] = str(exc)
        job["traceback"] = traceback.format_exc()
        job["updated_at"] = _now_iso()
        try:
            from tools.progress import report as emit_progress

            emit_progress("team_lead", f"任务失败：{exc}", phase="failed", status="failed", level="error")
        except Exception:
            pass
    finally:
        try:
            from tools.progress import unbind

            unbind()
        except Exception:
            pass


def start_investment_research(company: str, user_request: str = "") -> dict[str, Any]:
    company = (company or "").strip()
    if not company:
        raise ValueError("缺少公司名称或代码")

    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("未配置 OPENAI_API_KEY，无法启动投研分析")

    _ensure_agent_deps()

    from tools.progress import init_agents_state

    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "company": company,
        "type": "investment_research",
        "status": "running",
        "progress": [],
        "agents": init_agents_state(),
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
        target=_run_research_job,
        args=(job_id, company, user_request),
        daemon=True,
        name=f"ai-research-{job_id}",
    )
    thread.start()
    return public_research_job(job)


def get_research_job(job_id: str, *, include_full_result: bool = True) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        snapshot = job
    return public_research_job(snapshot, include_full_result=include_full_result)


def public_research_job(job: dict[str, Any], *, include_full_result: bool = True) -> dict[str, Any]:
    activity_log = job.get("activity_log") or []
    if len(activity_log) > 120:
        activity_log = activity_log[-120:]

    out = {
        "id": job["id"],
        "company": job["company"],
        "type": "investment_research",
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
        if include_full_result:
            out["result"] = result
        else:
            out["result"] = {
                "report_path": result.get("report_path", ""),
                "stock_code": result.get("stock_code", ""),
                "stock_name": result.get("stock_name", ""),
                "info_richness": result.get("info_richness", ""),
                "ready": True,
            }
    if job["status"] == "failed":
        out["error"] = job.get("error", "未知错误")
    return out


def list_research_reports() -> list[dict[str, Any]]:
    if not _REPORTS_DIR.exists():
        return []
    rows = []
    for path in sorted(_REPORTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not any(tag in path.name for tag in _RESEARCH_REPORT_RE):
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


def read_research_report(filename: str) -> str:
    safe = Path(filename).name
    path = _REPORTS_DIR / safe
    if not path.exists():
        raise FileNotFoundError(f"报告不存在: {safe}")
    return path.read_text(encoding="utf-8")
