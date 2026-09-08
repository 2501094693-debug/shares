"""基于项目 backend/company 接口的业务简述数据采集。

信息来源仅限：交易所（沪深北）、巨潮资讯、七家指定披露媒体官网。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from config import BACKEND_ROOT, DATA_LOOKBACK_DAYS

logger = logging.getLogger(__name__)

# 七家指定披露媒体（与 backend company.news.taxonomy.constants.PRESS_OUTLETS 一致）
OFFICIAL_PRESS_OUTLETS: tuple[tuple[str, str], ...] = (
    ("cs", "中证网"),
    ("cnstock", "中国证券网"),
    ("stcn", "证券时报网"),
    ("zqrb", "证券日报网"),
    ("financialnews", "金融时报网"),
    ("jjckb", "经济参考网"),
    ("chinadaily", "中国日报网"),
)

OFFICIAL_SOURCE_LABELS: tuple[str, ...] = (
    "上海证券交易所 / 深圳证券交易所 / 北京证券交易所",
    "巨潮资讯网",
    "、".join(name for _, name in OFFICIAL_PRESS_OUTLETS),
)

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _import_backend():
    from company.news.query import (
        query_cninfo,
        query_exchange,
        query_press,
        resolve_keywords,
    )
    from core.codes import detect_market, normalize_code

    return {
        "query_cninfo": query_cninfo,
        "query_exchange": query_exchange,
        "query_press": query_press,
        "resolve_keywords": resolve_keywords,
        "detect_market": detect_market,
        "normalize_code": normalize_code,
    }


def resolve_company(company: str) -> dict[str, str]:
    """解析公司名/代码 → code, name, keyword, market。"""
    api = _import_backend()
    resolved = api["resolve_keywords"](company)
    code = resolved.get("code") or api["normalize_code"](company) or company
    name = resolved.get("name") or ""
    market = api["detect_market"](code) if code else "unknown"
    return {
        "code": code,
        "name": name or company,
        "keyword": resolved.get("keyword") or name or company,
        "market": market,
    }


def _fmt_items(items: list[dict[str, Any]], *, limit: int = 20) -> str:
    if not items:
        return "（无数据）"
    lines = []
    for i, item in enumerate(items[:limit], 1):
        title = item.get("title") or item.get("name") or "无标题"
        pub = str(item.get("published_at") or item.get("date") or "")[:19]
        source = item.get("source") or item.get("channel") or item.get("media_name") or ""
        url = item.get("url") or ""
        summary = (item.get("summary") or item.get("abstract") or "")[:200]
        line = f"{i}. [{pub}] {title}"
        if source:
            line += f" | 来源: {source}"
        if url:
            line += f"\n   链接: {url}"
        if summary:
            line += f"\n   摘要: {summary}"
        lines.append(line)
    return "\n".join(lines)


_BUSINESS_NOTICE_KEYWORDS = (
    "经营", "业务", "产品", "营收", "收入", "订单", "项目", "投产", "合作",
    "收购", "并购", "产能", "销量", "客户", "合同", "中标", "研发", "年报",
    "半年报", "季报", "业绩", "盈利", "分部", "主营业务",
)


def _filter_business_notices(items: list[dict[str, Any]], limit: int = 30) -> list[dict[str, Any]]:
    business: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for item in items:
        title = (item.get("title") or "").lower()
        if any(kw in title for kw in _BUSINESS_NOTICE_KEYWORDS):
            business.append(item)
        else:
            other.append(item)
    return (business + other)[:limit]


def _safe_call(label: str, fn, *args, **kwargs) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.warning("%s 失败: %s", label, exc)
        return None


PERIODIC_KINDS: tuple[tuple[str, str], ...] = (
    ("annual", "年报"),
    ("semi", "半年报"),
    ("q1", "一季报"),
    ("q3", "三季报"),
)


def _merge_notice_items(*packs: dict[str, Any] | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for pack in packs:
        if pack and isinstance(pack, dict):
            items.extend(pack.get("items") or [])
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        title = item.get("title") or ""
        pub = str(item.get("published_at") or item.get("date") or "")[:10]
        key = f"{title}|{pub}"
        if title and key not in seen:
            seen.add(key)
            unique.append(item)
    unique.sort(
        key=lambda x: str(x.get("published_at") or x.get("date") or ""),
        reverse=True,
    )
    return unique


def _fetch_periodic_reports(
    code: str,
    name: str,
    *,
    days: int | None = None,
    limit_per_kind: int = 6,
) -> str:
    window = days if days is not None else DATA_LOOKBACK_DAYS
    api = _import_backend()
    blocks: list[str] = []

    for kind, label in PERIODIC_KINDS:
        cninfo_pack = _safe_call(
            f"巨潮{label}",
            api["query_cninfo"],
            code,
            category=kind,
            days=window,
            max_pages=5,
            limit=limit_per_kind,
        )
        exchange_pack = _safe_call(
            f"交易所{label}",
            api["query_exchange"],
            code,
            category=kind,
            days=window,
            max_pages=5,
            limit=limit_per_kind,
        )
        items = _merge_notice_items(cninfo_pack, exchange_pack)[:limit_per_kind]
        blocks.append(f"#### {label}（近{window}天，{len(items)} 条）\n{_fmt_items(items, limit=limit_per_kind)}")

    header = f"### 定期报告公告（{name} {code}，近{window}天）\n"
    return header + "\n\n".join(blocks)


def _fetch_business_notices(
    code: str,
    name: str,
    *,
    days: int | None = None,
    limit: int = 40,
) -> str:
    """从巨潮 + 所属交易所拉取经营相关公告。"""
    window = days if days is not None else DATA_LOOKBACK_DAYS
    api = _import_backend()

    cninfo_pack = _safe_call(
        "巨潮公告",
        api["query_cninfo"],
        code,
        days=window,
        max_pages=6,
        limit=60,
    )
    exchange_pack = _safe_call(
        "交易所公告",
        api["query_exchange"],
        code,
        days=window,
        max_pages=6,
        limit=60,
    )
    items = _filter_business_notices(
        _merge_notice_items(cninfo_pack, exchange_pack),
        limit=limit,
    )
    header = f"### 经营相关公告（{name} {code}，近{window}天，{len(items)} 条）\n"
    return header + _fmt_items(items, limit=limit)


def _fetch_press_coverage(
    code: str,
    name: str,
    *,
    days: int | None = None,
    limit_per_outlet: int = 12,
) -> str:
    """从七家指定披露媒体官网拉取公司相关报道。"""
    window = days if days is not None else DATA_LOOKBACK_DAYS
    api = _import_backend()
    pack = _safe_call(
        "七网",
        api["query_press"],
        code or name,
        days=window,
        max_pages=4,
        limit=limit_per_outlet * len(OFFICIAL_PRESS_OUTLETS),
    )
    if not pack or not isinstance(pack, dict):
        return "（未能获取七网报道）"

    by_outlet: dict[str, list[dict[str, Any]]] = pack.get("outlets") or {}
    blocks: list[str] = []
    total = 0

    for oid, label in OFFICIAL_PRESS_OUTLETS:
        rows = by_outlet.get(oid) or []
        if not rows:
            continue
        filtered = _filter_business_notices(rows, limit=limit_per_outlet)
        if not filtered:
            filtered = rows[:limit_per_outlet]
        total += len(filtered)
        blocks.append(f"#### {label}（{len(filtered)} 条）\n{_fmt_items(filtered, limit=limit_per_outlet)}")

    if not blocks:
        flat = pack.get("items") or []
        if flat:
            filtered = _filter_business_notices(flat, limit=30)
            blocks.append(_fmt_items(filtered or flat[:30], limit=30))
            total = len(filtered or flat[:30])

    header = f"### 七网相关报道（{name} {code}，近{window}天，共 {total} 条）\n"
    return header + ("\n\n".join(blocks) if blocks else "（无相关报道）")


def fetch_business_explainer_data(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    progress_node: str = "be_fetch",
) -> dict[str, Any]:
    """采集指定公司近一年业务简述资料。"""
    from tools.progress import report

    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    node = progress_node
    sections: dict[str, str] = {}
    sources: list[str] = []
    errors: list[str] = []

    report(node, f"采集 {name} 近 {DATA_LOOKBACK_DAYS} 天业务资料", phase="fetch_data", status="running")
    sources.extend(OFFICIAL_SOURCE_LABELS)

    report(node, "正在拉取定期报告公告（交易所 + 巨潮）…", phase="fetch_section")
    sections["定期报告"] = _fetch_periodic_reports(code, name)

    report(node, "正在拉取经营相关公告（交易所 + 巨潮）…", phase="fetch_section")
    notices_text = _fetch_business_notices(code, name)
    if "（无数据）" not in notices_text and "0 条" not in notices_text:
        sections["经营相关公告"] = notices_text

    report(node, "正在拉取七网相关报道…", phase="fetch_section")
    press_text = _fetch_press_coverage(code, name)
    if "（无相关报道）" not in press_text and "（未能获取" not in press_text:
        sections["七网报道"] = press_text

    window_note = (
        f"> **范围**：仅 {name}（{code}）· 近 {DATA_LOOKBACK_DAYS} 天 · "
        f"信息来源仅限：交易所、巨潮资讯、七家指定披露媒体官网\n\n"
    )
    text_parts = [window_note]
    for title, body in sections.items():
        text_parts.append(f"## {title}\n{body}")
    text = "\n\n".join(text_parts) if sections else (
        "（未能获取任何结构化数据，请基于已知信息分析并标注数据缺口）"
    )

    report(node, f"采集完成：{len(sections)} 类数据", phase="fetch_data_done", status="running")

    return {
        "code": code,
        "name": name,
        "market": resolved.get("market", ""),
        "sections": sections,
        "text": text,
        "sources_used": sources,
        "errors": errors,
        "data_available": bool(sections),
    }
