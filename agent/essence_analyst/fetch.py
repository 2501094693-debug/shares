"""第一步官方资料：交易所 / 巨潮 / 七网 / 公告 PDF。不取财报数字。"""

from __future__ import annotations

from typing import Any

from agent.config import DATA_LOOKBACK_DAYS
from agent.tools.data_fetcher import (
    OFFICIAL_SOURCE_LABELS,
    _collect_business_notices,
    _collect_periodic_items,
    _fetch_press_coverage,
    _fmt_items,
    _format_periodic_catalog,
)
from agent.tools.notice_pdf import (
    ingest_notice_pdfs,
    pick_latest_full_report,
    pick_notice_pdfs,
)
from agent.tools.progress import report as emit

_SECTION_ORDER = (
    "公告 PDF 正文",
    "定期报告目录",
    "经营相关公告",
    "七网报道",
)


def assemble_official_text(
    sections: dict[str, str],
    *,
    name: str,
    code: str,
) -> str:
    note = (
        f"> **主线范围**：仅 {name}（{code}）官方公告\n"
        f"> 来源：交易所、巨潮资讯、公告 PDF 正文、七家指定披露媒体官网\n"
        f"> 窗口：近 {DATA_LOOKBACK_DAYS} 天；定期报告取各类型最新一期全文 PDF，用来读主营业务描述\n"
        f"> 不采集东财 F10 报表、分部收入表、历史财报数字。\n"
        f"> 冲突时：公告 PDF 正文优于公告标题。\n\n"
    )
    parts = [note]
    for title in _SECTION_ORDER:
        body = (sections.get(title) or "").strip()
        if body:
            parts.append(f"## {title}\n{body}")
    for title, body in sections.items():
        if title in _SECTION_ORDER:
            continue
        if body and str(body).strip():
            parts.append(f"## {title}\n{body}")
    return "\n\n".join(parts)


def _pick_official_pdfs(
    periodic_by_kind: dict[str, list[dict[str, Any]]],
    notice_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for items in periodic_by_kind.values():
        picked = pick_latest_full_report(items)
        url = (picked or {}).get("url") or ""
        if picked and url not in seen:
            targets.append(picked)
            seen.add(url)
    targets.extend(pick_notice_pdfs(notice_items, already=targets, limit=5))
    return targets


def fetch_essence_official(
    company: str,
    stock: dict[str, str],
    *,
    progress_node: str = "es_official",
) -> dict[str, Any]:
    """第一步资料：官方公告，不含财报数字。"""
    code = stock["code"]
    name = stock["name"]
    node = progress_node
    sections: dict[str, str] = {}
    sources: list[str] = list(OFFICIAL_SOURCE_LABELS)
    errors: list[str] = []

    emit(node, f"采集 {name} 官方公告（交易所 / 巨潮 / 七网）", phase="fetch_data", status="running")

    emit(node, "正在拉取定期报告公告目录…", phase="fetch_section")
    periodic_by_kind = _collect_periodic_items(code, name)
    sections["定期报告目录"] = _format_periodic_catalog(periodic_by_kind, name, code)

    emit(node, "正在拉取经营相关公告…", phase="fetch_section")
    notice_items = _collect_business_notices(code, name)
    if notice_items:
        sections["经营相关公告"] = (
            f"### 经营相关公告目录（{name} {code}，近 {DATA_LOOKBACK_DAYS} 天，{len(notice_items)} 条）\n"
            + _fmt_items(notice_items, limit=40)
        )

    pdf_targets = _pick_official_pdfs(periodic_by_kind, notice_items)
    if pdf_targets:
        emit(node, f"正在下载并抽取 {len(pdf_targets)} 份公告 PDF 正文…", phase="fetch_pdf")
        pdf_text = ingest_notice_pdfs(
            pdf_targets,
            code=code,
            progress=lambda msg: emit(node, msg, phase="fetch_pdf"),
        )
        if pdf_text:
            sections["公告 PDF 正文"] = pdf_text
            sources.append("公告 PDF 正文（巨潮/交易所）")

    emit(node, "正在拉取七网相关报道…", phase="fetch_section")
    press_text = _fetch_press_coverage(code, name)
    if "（无相关报道）" not in press_text and "（未能获取" not in press_text:
        sections["七网报道"] = press_text

    text = assemble_official_text(sections, name=name, code=code)
    emit(node, f"官方披露完成：{len(sections)} 类", phase="fetch_data_done", status="done")
    return {
        "text": text,
        "sections": sections,
        "sources_used": sources,
        "errors": errors,
        "pdf_count": len(pdf_targets),
    }
