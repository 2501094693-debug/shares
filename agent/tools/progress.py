"""线程内进度上报：供业务简述 / 巴菲特读表等 LangGraph 节点与 data_fetcher 写入当前任务状态。"""

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
    "bf_init": "解析公司",
    "bf_fetch": "采集数据",
    "bf_understand": "一、生意能否看懂",
    "bf_owner": "二、所有者盈余",
    "bf_capital": "三、资本饥饿",
    "bf_honesty": "四、会计与配置",
    "bf_synthesis": "五、综合判决",
    "bf_assemble": "拼装报告",
    "bf_save": "保存报告",
    "rs_init": "解析公司",
    "rs_fetch_em": "采集东财股吧",
    "rs_fetch_ths": "采集同花顺讨论",
    "rs_fetch_xq": "采集雪球讨论",
    "rs_merge": "合并语料",
    "rs_filter": "识别散户",
    "rs_classify": "标注立场与行动",
    "rs_agg": "按用户计数",
    "rs_synth": "生成解读",
    "rs_save": "保存报告",
    "va_init": "解析公司",
    "va_fetch": "采集估值数据",
    "va_history": "历史倍数",
    "va_fundamentals": "财报正常化",
    "va_buffett": "巴菲特路径",
    "va_drivers": "收入关键因素",
    "va_synth": "交叉对照",
    "va_save": "保存报告",
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
    "analyze": "规则分析",
    "save_file": "写入文件",
    "skip": "跳过",
    "done": "已完成",
    "failed": "失败",
}

ALL_AGENTS = ["be_init", "be_fetch", "be_search", "be_explain", "be_save"]
RETAIL_AGENTS = [
    "rs_init",
    "rs_fetch_em",
    "rs_fetch_ths",
    "rs_fetch_xq",
    "rs_merge",
    "rs_filter",
    "rs_classify",
    "rs_agg",
    "rs_synth",
    "rs_save",
]
VALUATION_AGENTS = [
    "va_init",
    "va_fetch",
    "va_history",
    "va_fundamentals",
    "va_buffett",
    "va_drivers",
    "va_synth",
    "va_save",
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


def init_retail_sentiment_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(RETAIL_AGENTS)


def init_valuation_analyst_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(VALUATION_AGENTS)


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
