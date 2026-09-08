"""投研团队进度上报。"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_job: dict[str, Any] | None = None

AGENT_LABELS: dict[str, str] = {
    "init": "初始化",
    "business_analyst": "商业模式分析师",
    "financial_analyst": "财务分析师",
    "industry_researcher": "行业研究员",
    "risk_assessor": "风险评估师",
    "team_lead": "团队负责人",
    "save": "保存报告",
    "audit": "数据抽检",
}

PHASE_LABELS: dict[str, str] = {
    "start": "启动",
    "resolve": "解析标的",
    "assess": "信息丰富度评估",
    "fetch_data": "采集数据",
    "fetch_section": "采集数据",
    "llm": "LLM 分析",
    "synthesize": "汇总报告",
    "save_file": "写入文件",
    "audit_extract": "抽检提取",
    "done": "已完成",
    "failed": "失败",
}

ALL_AGENTS = [
    "init",
    "business_analyst",
    "financial_analyst",
    "industry_researcher",
    "risk_assessor",
    "team_lead",
    "save",
    "audit",
]


def normalize_node(node: str) -> str:
    return (node or "").replace("-", "_")


def bind(job: dict[str, Any], lock: threading.Lock | None = None) -> None:
    global _job, _lock
    _job = job
    if lock is not None:
        _lock = lock


def unbind() -> None:
    global _job
    _job = None


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def init_agents_state() -> dict[str, dict[str, str]]:
    return {
        key: {
            "status": "pending",
            "phase": "",
            "message": "等待中",
            "updated_at": "",
        }
        for key in ALL_AGENTS
    }


def report(
    node: str,
    message: str,
    *,
    phase: str = "",
    status: str = "running",
    level: str = "info",
) -> None:
    node_key = normalize_node(node)
    entry = {
        "node": node_key,
        "label": AGENT_LABELS.get(node_key, node_key),
        "phase": phase,
        "phase_label": PHASE_LABELS.get(phase, phase),
        "message": message,
        "status": status,
        "level": level,
        "at": _now(),
    }
    with _lock:
        if not _job:
            return
        log = _job.setdefault("activity_log", [])
        log.append(entry)
        if len(log) > 200:
            _job["activity_log"] = log[-200:]

        _job["current"] = {
            "node": node_key,
            "label": entry["label"],
            "phase": phase,
            "phase_label": entry["phase_label"],
            "message": message,
            "at": entry["at"],
        }

        agents = _job.setdefault("agents", {})
        if node_key in agents:
            agents[node_key] = {
                "status": status,
                "phase": phase,
                "phase_label": entry["phase_label"],
                "message": message,
                "updated_at": entry["at"],
            }
        _job["updated_at"] = entry["at"]
