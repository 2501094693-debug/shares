"""线程内进度上报：供业务简述 / 财报解读 LangGraph 节点与 data_fetcher 写入当前任务状态。"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_job: dict[str, Any] | None = None

AGENT_LABELS: dict[str, str] = {
    "be_init": "解析公司",
    "be_fetch": "采集资料",
    "be_search": "联网补充",
    "be_explain": "生成简述",
    "be_save": "保存报告",
    "er_init": "解析公司",
    "er_fetch": "采集财报",
    "er_explain": "生成解读",
    "er_save": "保存报告",
}

PHASE_LABELS: dict[str, str] = {
    "start": "启动",
    "resolve": "解析标的",
    "fetch_data": "采集数据",
    "fetch_section": "采集数据",
    "fetch_pdf": "抽取公告 PDF",
    "fetch_data_done": "数据采集完成",
    "web_search": "联网补充",
    "web_search_done": "联网补充完成",
    "web_search_skip": "跳过联网",
    "llm": "LLM 生成",
    "llm_done": "生成完成",
    "save_file": "写入文件",
    "done": "已完成",
    "failed": "失败",
}

ALL_AGENTS = ["be_init", "be_fetch", "be_search", "be_explain", "be_save"]
EARNINGS_AGENTS = ["er_init", "er_fetch", "er_explain", "er_save"]


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


def init_agents_state(keys: list[str] | None = None) -> dict[str, dict[str, str]]:
    return {
        key: {
            "status": "pending",
            "phase": "",
            "message": "等待中",
            "updated_at": "",
        }
        for key in (keys or ALL_AGENTS)
    }


def init_business_explainer_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(ALL_AGENTS)


def init_earnings_reviewer_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(EARNINGS_AGENTS)


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
