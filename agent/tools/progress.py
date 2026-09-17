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
    "ic_init": "解析公司",
    "ic_fetch": "采集资料",
    "ic_search": "联网补充",
    "ic_analyze": "生成分析",
    "ic_save": "保存报告",
    "rr_init": "解析公司",
    "rr_fetch": "采集资料",
    "rr_search": "联网补充",
    "rr_analyze": "生成评估",
    "rr_save": "保存报告",
    "ca_init": "解析公司",
    "ca_fetch": "采集数据",
    "ca_business": "业务分析",
    "ca_balance": "资产负债表",
    "ca_income": "利润表",
    "ca_cashflow": "现金流量表",
    "ca_synthesis": "三表汇总",
    "ca_valuation": "估值分析",
    "ca_search": "市场信息",
    "ca_outlook": "前景研判",
    "ca_assemble": "拼装报告",
    "ca_save": "保存报告",
    "bz_init": "解析公司",
    "bz_fetch": "采集数据",
    "bz_strategy": "一看：战略",
    "bz_operating": "二看：经营资产",
    "bz_profit": "三看：效益质量",
    "bz_value": "四看：价值",
    "bz_cost": "五看：成本机制",
    "bz_quality": "六看：财务状况",
    "bz_risk": "七看：风险",
    "bz_outlook": "八看：前景",
    "bz_synthesis": "综合诊断",
    "bz_assemble": "拼装报告",
    "bz_save": "保存报告",
    "bf_init": "解析公司",
    "bf_fetch": "采集数据",
    "bf_understand": "一、生意能否看懂",
    "bf_owner": "二、所有者盈余",
    "bf_capital": "三、资本饥饿",
    "bf_honesty": "四、会计与配置",
    "bf_synthesis": "五、综合判决",
    "bf_assemble": "拼装报告",
    "bf_save": "保存报告",
    "dy_init": "解析公司",
    "dy_fetch": "采集数据",
    "dy_business": "一、生意模式",
    "dy_culture": "二、企业文化",
    "dy_price": "三、好价钱",
    "dy_synthesis": "四、能不能看懂",
    "dy_assemble": "拼装报告",
    "dy_save": "保存报告",
    "es_resolve": "解析公司",
    "es_official": "官方公告",
    "es_businesses": "主营确认",
    "es_web": "联网补充",
    "es_explain": "讲清业务",
    "es_factors": "关键因素",
    "es_save": "保存报告",
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
    "critique": "质疑复核",
    "confirm": "确认通过",
    "extra_search": "补证据",
    "save_file": "写入文件",
    "skip": "跳过",
    "done": "已完成",
    "failed": "失败",
}

ALL_AGENTS = ["be_init", "be_fetch", "be_search", "be_explain", "be_save"]
COMPETITION_AGENTS = ["ic_init", "ic_fetch", "ic_search", "ic_analyze", "ic_save"]
RISK_REVIEWER_AGENTS = ["rr_init", "rr_fetch", "rr_search", "rr_analyze", "rr_save"]
COMPREHENSIVE_AGENTS = [
    "ca_init",
    "ca_fetch",
    "ca_business",
    "ca_balance",
    "ca_income",
    "ca_cashflow",
    "ca_synthesis",
    "ca_valuation",
    "ca_search",
    "ca_outlook",
    "ca_assemble",
    "ca_save",
]
BAZHANG_AGENTS = [
    "bz_init",
    "bz_fetch",
    "bz_strategy",
    "bz_operating",
    "bz_profit",
    "bz_value",
    "bz_cost",
    "bz_quality",
    "bz_risk",
    "bz_outlook",
    "bz_synthesis",
    "bz_assemble",
    "bz_save",
]
BUFFETT_AGENTS = [
    "bf_init",
    "bf_fetch",
    "bf_understand",
    "bf_owner",
    "bf_capital",
    "bf_honesty",
    "bf_synthesis",
    "bf_assemble",
    "bf_save",
]
DUAN_AGENTS = [
    "dy_init",
    "dy_fetch",
    "dy_business",
    "dy_culture",
    "dy_price",
    "dy_synthesis",
    "dy_assemble",
    "dy_save",
]
ESSENCE_AGENTS = [
    "es_resolve",
    "es_official",
    "es_businesses",
    "es_web",
    "es_explain",
    "es_factors",
    "es_save",
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


def init_industry_competition_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(COMPETITION_AGENTS)


def init_risk_reviewer_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(RISK_REVIEWER_AGENTS)


def init_comprehensive_analyst_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(COMPREHENSIVE_AGENTS)


def init_bazhang_analyst_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(BAZHANG_AGENTS)


def init_buffett_analyst_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(BUFFETT_AGENTS)


def init_duan_analyst_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(DUAN_AGENTS)


def init_essence_analyst_agents() -> dict[str, dict[str, str]]:
    return init_agents_state(ESSENCE_AGENTS)


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
