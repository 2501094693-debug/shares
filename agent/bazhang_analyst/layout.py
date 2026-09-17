"""八看报告排版：固定章节骨架，模型只填正文。"""

from __future__ import annotations

import re
from typing import Any

SCAFFOLD_HEADINGS = {"解读", "原始数据", "本章小结", "综合诊断"}
SECTION_PREFIXES = ("一看", "二看", "三看", "四看", "五看", "六看", "七看", "八看")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SUMMARY_RE = re.compile(r"(?:^|\n)(?:#{1,6}\s*)?本章小结[：:：]?\s*")
BLANK_RE = re.compile(r"\n{3,}")

SECTION_ORDER = (
    "一看：战略——资源配置揭示什么？",
    "二看：经营资产管理与竞争力",
    "三看：效益与质量（核心利润视角）",
    "四看：价值创造",
    "五看：成本决定机制",
    "六看：财务状况质量",
    "七看：风险",
    "八看：前景",
    "综合诊断",
)

MIN_PROSE_CHARS = 40


def llm_text(content: Any) -> str:
    """从 ChatOpenAI / LangChain 返回值中抽出纯文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content") or ""
                if text:
                    parts.append(str(text))
            else:
                text = getattr(block, "text", None) or getattr(block, "content", None)
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()
    return str(content).strip()


def _heading_core(text: str) -> str:
    return text.strip().strip("：:：").strip()


def _is_scaffold_heading(heading: str, title: str) -> bool:
    core = _heading_core(heading)
    if not core:
        return True
    if core in SCAFFOLD_HEADINGS:
        return True
    title_core = _heading_core(title)
    title_prefix = title_core.split("：")[0] if title_core else ""
    if title_core and (core == title_core or core == title_prefix):
        return True
    if title_prefix and (core.startswith(title_prefix) or title_core.startswith(core)):
        return True
    if core.startswith(SECTION_PREFIXES):
        return True
    return False


def strip_scaffold_headings(text: str, title: str = "") -> str:
    """去掉模型重复输出的章节/解读标题；其余标题降为加粗，避免打乱骨架。"""
    if not text:
        return ""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        match = HEADING_RE.match(raw.strip())
        if not match:
            lines.append(raw.rstrip())
            continue
        heading = match.group(2).strip()
        if _is_scaffold_heading(heading, title):
            continue
        lines.append(f"**{_heading_core(heading)}**")
    cleaned = "\n".join(lines).strip()
    return BLANK_RE.sub("\n\n", cleaned)


def split_summary(text: str) -> tuple[str, str]:
    """把「本章小结」从正文中拆出，供骨架固定放置。"""
    if not text:
        return "", ""
    matches = list(SUMMARY_RE.finditer(text))
    if not matches:
        return text.strip(), ""
    hit = matches[-1]
    body = text[: hit.start()].strip()
    summary = text[hit.end() :].strip()
    summary = strip_scaffold_headings(summary, "本章小结")
    return body, summary


def normalize_section(content: str, title: str = "") -> tuple[str, str]:
    """返回 (解读正文, 本章小结)。先拆小结，再剥标题，避免「本章小结」被当骨架标题丢掉。"""
    body, summary = split_summary(content or "")
    body = strip_scaffold_headings(body, title)
    summary = strip_scaffold_headings(summary, "本章小结")
    return body.strip(), summary.strip()


def prose_char_count(text: str, title: str = "") -> int:
    body, summary = normalize_section(text, title)
    merged = re.sub(r"\s+", "", body + summary)
    return len(merged)


def has_prose(text: str, title: str = "") -> bool:
    return prose_char_count(text, title) >= MIN_PROSE_CHARS


def rule_engine_fallback(title: str, table: str = "", zhang_summary: str = "") -> str:
    evidence = (table or "").strip() or (zhang_summary or "").strip() or "（无预计算表）"
    return (
        f"模型未完成本节解读，以下按规则引擎预计算直述，不替代完整质量判断。\n\n"
        f"{evidence}\n\n"
        f"本章小结：本节缺少模型解读，请以原始数据表与附录规则引擎摘要为准。"
    )


def render_section(title: str, table: str, content: str) -> str:
    body, summary = normalize_section(content, title)
    if not body:
        body = "（本节解读缺失）"
    if not summary:
        summary = "（模型未单独给出本章小结，请以上方解读为准。）"

    parts = [f"## {title}", ""]
    parts.append("### 原始数据")
    parts.append("")
    parts.append((table or "").strip() or "（本章无独立数据表，依据规则引擎摘要与前述各看。）")
    parts.append("")
    parts.append("### 解读")
    parts.append("")
    parts.append(body)
    parts.append("")
    parts.append("### 本章小结")
    parts.append("")
    parts.append(summary)
    return "\n".join(parts).rstrip() + "\n"


def flags_as_table(flags: list[str] | None) -> str:
    if not flags:
        return "- 暂无重大警示"
    return "\n".join(f"- {item}" for item in flags)
