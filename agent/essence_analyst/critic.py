"""质疑结果解析与硬规则。大模型判断之后，再用确定性规则拦一遍。"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
_BRACE = re.compile(r"\{.*\}", re.S)

_VERDICT_MAP = {
    "confirm": "confirm",
    "ok": "confirm",
    "pass": "confirm",
    "通过": "confirm",
    "确认": "confirm",
    "revise": "revise",
    "reject": "revise",
    "fail": "revise",
    "修改": "revise",
    "重写": "revise",
    "不通过": "revise",
    "need_evidence": "need_evidence",
    "need_more": "need_evidence",
    "evidence": "need_evidence",
    "补充": "need_evidence",
    "缺证据": "need_evidence",
}

_UNOFFICIAL_HINTS = ("雪球", "知乎", "同花顺研报", "卖方", "微信公众号", "小作文")
_BUFFETT_HINTS = ("所有者盈余", "巴菲特五问", "增量资本回报", "1 美元测试", "一美元测试")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def parse_critic(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    blob = ""
    fence = _FENCE.search(text)
    if fence:
        blob = fence.group(1)
    else:
        match = _BRACE.search(text)
        if match:
            blob = match.group(0)
    data: dict[str, Any] = {}
    if blob:
        try:
            loaded = json.loads(blob)
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            data = {}

    raw_verdict = str(data.get("verdict") or "").strip().lower()
    verdict = _VERDICT_MAP.get(raw_verdict, "")
    if not verdict:
        if "need_evidence" in text or "缺证据" in text or "补充检索" in text:
            verdict = "need_evidence"
        elif "不通过" in text or "revise" in text.lower() or "重写" in text:
            verdict = "revise"
        else:
            verdict = "revise"

    scope = str(data.get("search_scope") or "web").strip().lower()
    if scope not in {"official", "web"}:
        scope = "web"

    return {
        "verdict": verdict,
        "issues": _as_list(data.get("issues")),
        "required_fix": str(data.get("required_fix") or "").strip(),
        "search_query": str(data.get("search_query") or "").strip(),
        "search_scope": scope,
    }


def apply_hard_rules(
    *,
    stage: str,
    draft: str,
    parsed: dict[str, Any],
) -> dict[str, Any]:
    """大模型确认之后的硬闸：无来源、第一阶段用了非官方、写成巴菲特读表。"""
    out = dict(parsed)
    issues = list(out.get("issues") or [])
    verdict = out.get("verdict") or "revise"
    body = draft or ""

    if "〔来源" not in body and "来源：" not in body and "来源:" not in body:
        issues.append("正文未标注来源，不能确认")
        if verdict == "confirm":
            verdict = "revise"

    if stage == "businesses":
        for hint in _UNOFFICIAL_HINTS:
            if hint in body:
                issues.append(f"主营清单出现非官方痕迹「{hint}」")
                if verdict == "confirm":
                    verdict = "revise"
                break

    for hint in _BUFFETT_HINTS:
        if hint in body:
            issues.append(f"本章不应出现「{hint}」，本智能体不做巴菲特视角解读")
            if verdict == "confirm":
                verdict = "revise"
            break

    if verdict == "need_evidence" and not out.get("search_query"):
        verdict = "revise"
        issues.append("声称缺证据但没有给出检索词，改为退回重写")

    out["verdict"] = verdict
    out["issues"] = issues
    return out
