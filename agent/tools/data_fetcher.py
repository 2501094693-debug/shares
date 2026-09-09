"""业务简述数据采集。

主线来源：交易所（沪深北）、巨潮资讯、七家指定披露媒体官网。
补充来源：联网搜索最新财报解读、行业报告等公开网页（不得覆盖主线事实）。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from agent.config import BACKEND_ROOT, DATA_LOOKBACK_DAYS

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
    """解析公司名/代码 → 6 位股票代码。禁止把中文简称当成代码。"""
    api = _import_backend()
    raw = (company or "").strip()
    if not raw:
        raise ValueError("缺少公司名称或代码")

    resolved = api["resolve_keywords"](raw)
    code = api["normalize_code"](resolved.get("code") or "") or api["normalize_code"](raw)
    name = (resolved.get("name") or "").strip()

    if len(code) != 6:
        code, name = _resolve_from_stock_index(raw, name, api["normalize_code"])

    if len(code) != 6:
        raise ValueError(
            f"无法解析「{raw}」的股票代码。请输入 6 位代码，例如 600519 或 600990。"
        )

    market = api["detect_market"](code) if code else "unknown"
    return {
        "code": code,
        "name": name or raw,
        "keyword": resolved.get("keyword") or name or raw,
        "market": market,
    }


def _resolve_from_stock_index(
    company: str,
    name: str,
    normalize_code,
) -> tuple[str, str]:
    """申万成分股索引按简称兜底。"""
    try:
        from industry.service import service as industry

        industry.stocks.ensure_populated()
        rows = industry.search_stocks(name=company, limit=12) or []
        if not rows and name and name != company:
            rows = industry.search_stocks(name=name, limit=12) or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("行业索引解析失败 %s: %s", company, exc)
        return "", name

    if not rows:
        return "", name

    needle = (name or company).strip()
    exact = [row for row in rows if (row.get("name") or "").strip() == needle]
    hit = (exact or rows)[0]
    code = normalize_code(str(hit.get("code") or ""))
    title = str(hit.get("name") or "").strip()
    return (code if len(code) == 6 else ""), (title or name)


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

_COMPETITION_NOTICE_KEYWORDS = (
    "行业", "竞争", "市场", "份额", "产能", "价格", "中标", "订单", "合作",
    "并购", "收购", "上下游", "供应链", "技术", "政策", "监管", "进口", "出口",
    "年报", "半年报", "季报", "主营业务", "分部", "收入结构", "龙头", "对手",
    "同行", "投产", "扩产", "替代", "国产", "出口", "进口",
)

_RISK_NOTICE_KEYWORDS = (
    "风险", "监管", "处罚", "立案", "警示", "违规", "诉讼", "仲裁", "担保",
    "质押", "减持", "增持", "股权激励", "关联交易", "股权", "股东", "回购",
    "分红", "年报", "半年报", "季报", "审计", "内控", "董事", "高管", "管理层",
    "辞职", "聘任", "问询", "关注函", "监管函", "调查", "行政处罚", "退市",
    "ST", "停牌", "复牌", "承诺", "整改", "诚信", "独董", "实控人", "控制权",
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


def _filter_competition_notices(items: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for item in items:
        title = (item.get("title") or "").lower()
        if any(kw in title for kw in _COMPETITION_NOTICE_KEYWORDS):
            matched.append(item)
        else:
            other.append(item)
    return (matched + other)[:limit]


def _filter_risk_notices(items: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for item in items:
        title = (item.get("title") or "").lower()
        if any(kw in title for kw in _RISK_NOTICE_KEYWORDS):
            matched.append(item)
        else:
            other.append(item)
    return (matched + other)[:limit]


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
    from agent.tools.notice_pdf import prefer_cninfo_items

    unique = prefer_cninfo_items(items)
    unique.sort(
        key=lambda x: str(x.get("published_at") or x.get("date") or ""),
        reverse=True,
    )
    return unique


def _collect_periodic_items(
    code: str,
    name: str,
    *,
    days: int | None = None,
    limit_per_kind: int = 6,
) -> dict[str, list[dict[str, Any]]]:
    window = days if days is not None else DATA_LOOKBACK_DAYS
    api = _import_backend()
    by_kind: dict[str, list[dict[str, Any]]] = {}
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
        by_kind[label] = _merge_notice_items(cninfo_pack, exchange_pack)[:limit_per_kind]
    return by_kind


def _format_periodic_catalog(
    by_kind: dict[str, list[dict[str, Any]]],
    name: str,
    code: str,
    *,
    days: int | None = None,
) -> str:
    window = days if days is not None else DATA_LOOKBACK_DAYS
    blocks: list[str] = []
    for label, items in by_kind.items():
        blocks.append(f"#### {label}（近{window}天，{len(items)} 条）\n{_fmt_items(items, limit=6)}")
    header = f"### 定期报告公告目录（{name} {code}，近{window}天）\n"
    return header + "\n\n".join(blocks)


def _fetch_periodic_reports(
    code: str,
    name: str,
    *,
    days: int | None = None,
    limit_per_kind: int = 6,
) -> str:
    by_kind = _collect_periodic_items(code, name, days=days, limit_per_kind=limit_per_kind)
    return _format_periodic_catalog(by_kind, name, code, days=days)


def _collect_business_notices(
    code: str,
    name: str,
    *,
    days: int | None = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
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
    return _filter_business_notices(
        _merge_notice_items(cninfo_pack, exchange_pack),
        limit=limit,
    )


def _fetch_business_notices(
    code: str,
    name: str,
    *,
    days: int | None = None,
    limit: int = 40,
) -> str:
    """从巨潮 + 所属交易所拉取经营相关公告。"""
    window = days if days is not None else DATA_LOOKBACK_DAYS
    items = _collect_business_notices(code, name, days=days, limit=limit)
    header = f"### 经营相关公告目录（{name} {code}，近{window}天，{len(items)} 条）\n"
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
    from agent.tools.progress import report

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
    periodic_by_kind = _collect_periodic_items(code, name)
    sections["定期报告"] = _format_periodic_catalog(periodic_by_kind, name, code)

    report(node, "正在拉取经营相关公告（交易所 + 巨潮）…", phase="fetch_section")
    notice_items = _collect_business_notices(code, name)
    notices_text = (
        f"### 经营相关公告目录（{name} {code}，近 {DATA_LOOKBACK_DAYS} 天，{len(notice_items)} 条）\n"
        + _fmt_items(notice_items, limit=40)
    )
    if notice_items:
        sections["经营相关公告"] = notices_text

    from agent.tools.notice_pdf import ingest_notice_pdfs, pick_latest_full_report, pick_notice_pdfs

    pdf_targets: list[dict[str, Any]] = []
    for items in periodic_by_kind.values():
        picked = pick_latest_full_report(items)
        if picked:
            pdf_targets.append(picked)
    pdf_targets.extend(pick_notice_pdfs(notice_items, already=pdf_targets, limit=5))

    if pdf_targets:
        report(
            node,
            f"正在下载并抽取 {len(pdf_targets)} 份公告 PDF 正文…",
            phase="fetch_pdf",
        )
        pdf_text = ingest_notice_pdfs(
            pdf_targets,
            code=code,
            progress=lambda msg: report(node, msg, phase="fetch_pdf"),
        )
        if pdf_text:
            sections["公告 PDF 正文"] = pdf_text
            sources.append("公告 PDF 正文（巨潮/交易所）")

    report(node, "正在拉取七网相关报道…", phase="fetch_section")
    press_text = _fetch_press_coverage(code, name)
    if "（无相关报道）" not in press_text and "（未能获取" not in press_text:
        sections["七网报道"] = press_text

    window_note = (
        f"> **主线范围**：仅 {name}（{code}）· 近 {DATA_LOOKBACK_DAYS} 天 · "
        f"信息来源：交易所、巨潮资讯、公告 PDF 正文、七家指定披露媒体官网\n\n"
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


def fetch_web_supplement(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    progress_node: str = "be_search",
) -> dict[str, Any]:
    """联网搜索补充：最新财报、行业报告、护城河与客户价值公开信息。"""
    from agent.tools.progress import report
    from agent.tools.web_search import search_for_business, web_search_status

    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    available, engine_hint = web_search_status()
    if not available:
        report(progress_node, engine_hint, phase="web_search_skip", status="done")
        return {
            "text": "",
            "engines": [],
            "used": False,
            "sources_used": [],
        }

    report(
        progress_node,
        f"联网补充检索（{engine_hint}）…",
        phase="web_search",
        status="running",
    )

    def _on_query(query: str) -> None:
        report(progress_node, f"检索：{query}", phase="web_search")

    text, engines = search_for_business(
        name,
        stock_code=code,
        progress_cb=_on_query,
    )
    used = bool(text)
    if used:
        engine_label = "+".join(engines) if engines else engine_hint
        sources = [f"联网搜索（{engine_label}）"]
        report(
            progress_node,
            f"联网补充完成（{engine_label}）",
            phase="web_search_done",
            status="running",
        )
    else:
        report(
            progress_node,
            "联网搜索未返回有效结果，将仅依据官方披露撰写",
            phase="web_search_done",
            status="running",
            level="warn",
        )
        sources = []

    header = (
        f"> **补充范围**：{name}（{code}）的公开网页检索；"
        "数字与事实若与交易所/巨潮冲突，以官方披露为准。\n\n"
    )
    return {
        "text": (header + text) if text else "",
        "engines": engines,
        "used": used,
        "sources_used": sources,
    }


def _fetch_profile_pack(code: str, name: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    """公司画像：盘口估值 + 申万行业。"""
    try:
        from company.profile import get_stock_profile
        from agent.tools.financials import format_profile_table
    except Exception as exc:  # noqa: BLE001
        logger.warning("画像导入失败: %s", exc)
        return {}, {}, f"（未能导入公司画像：{exc}）"

    pack = _safe_call("公司画像", get_stock_profile, code, name=name)
    if not pack or not isinstance(pack, dict):
        return {}, {}, "（未能获取公司画像）"
    stock = pack.get("stock") or {}
    industry = pack.get("industry") or {}
    text = f"### 公司画像与盘口\n{format_profile_table(stock, industry)}"
    return stock, industry, text


def fetch_earnings_reviewer_data(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    progress_node: str = "er_fetch",
) -> dict[str, Any]:
    """采集指定公司近一年财报解读资料：报表原始科目 + 估值 + 定期报告公告。"""
    from agent.tools.financials import (
        build_valuation_helpers,
        fetch_financial_pack,
        fetch_valuation_pack,
    )
    from agent.tools.progress import report

    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    node = progress_node
    sections: dict[str, str] = {}
    sources: list[str] = []
    errors: list[str] = []

    report(node, f"采集 {name} 近一年财报与估值数据", phase="fetch_data", status="running")

    report(node, "正在拉取公司画像与盘口估值…", phase="fetch_section")
    profile_stock, industry, profile_text = _fetch_profile_pack(code, name)
    if "未能" not in profile_text:
        sections["公司画像与盘口"] = profile_text
        sources.extend(["东方财富盘口", "申万行业"])

    report(node, "正在拉取利润表 / 资产负债表 / 现金流量表…", phase="fetch_section")
    fin = fetch_financial_pack(code, name)
    errors.extend(fin.get("errors") or [])
    if fin.get("text") and "未能获取" not in fin["text"]:
        sections["财务报表原始数据"] = fin["text"]
        sources.extend(fin.get("sources") or [])

    report(node, "正在拉取历史估值与同业对比…", phase="fetch_section")
    val = fetch_valuation_pack(code, name, profile_stock, industry)
    if val.get("text"):
        sections["估值与同业"] = val["text"]
        sources.extend(val.get("sources") or [])
    helpers = build_valuation_helpers(
        profile_stock,
        fin.get("annual") or [],
        val.get("pe_items") or [],
    )
    sections["安全边际预计算"] = helpers

    report(node, "正在拉取近一年定期报告公告（交易所 + 巨潮）…", phase="fetch_section")
    sections["定期报告公告"] = _fetch_periodic_reports(code, name)
    sources.extend(OFFICIAL_SOURCE_LABELS)

    window_note = (
        f"> **任务**：解读 {name}（{code}）最近一年财报。"
        f"趋势用近 3-5 年年报对照；估值用当前盘口、历史分位与同业。"
        f"每段解释必须引用下方原始数据，禁止用训练知识填数。\n\n"
    )
    text_parts = [window_note]
    for title, body in sections.items():
        text_parts.append(f"## {title}\n{body}")
    text = "\n\n".join(text_parts) if sections else (
        "（未能获取任何结构化数据，请诚实标注数据缺口，禁止编造财务数字）"
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


def _collect_competition_notices(
    code: str,
    name: str,
    *,
    days: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    window = days if days is not None else DATA_LOOKBACK_DAYS
    api = _import_backend()
    cninfo_pack = _safe_call(
        "巨潮公告",
        api["query_cninfo"],
        code,
        days=window,
        max_pages=6,
        limit=80,
    )
    exchange_pack = _safe_call(
        "交易所公告",
        api["query_exchange"],
        code,
        days=window,
        max_pages=6,
        limit=80,
    )
    return _filter_competition_notices(
        _merge_notice_items(cninfo_pack, exchange_pack),
        limit=limit,
    )


def _fetch_peer_competition_table(code: str, name: str) -> str:
    """申万三级行业成分股与同业估值对照。"""
    try:
        from agent.tools.financials import _peer_table
    except Exception as exc:  # noqa: BLE001
        logger.warning("同业对照导入失败: %s", exc)
        return f"（未能导入同业对照：{exc}）"
    return _peer_table(code, name)


def fetch_industry_competition_data(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    progress_node: str = "ic_fetch",
) -> dict[str, Any]:
    """采集指定公司行业竞争分析资料：官方披露 + 同业对照。"""
    from agent.tools.progress import report

    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    node = progress_node
    sections: dict[str, str] = {}
    sources: list[str] = []
    errors: list[str] = []
    industry_name = ""
    industry_code = ""

    report(node, f"采集 {name} 近 {DATA_LOOKBACK_DAYS} 天行业竞争资料", phase="fetch_data", status="running")
    sources.extend(OFFICIAL_SOURCE_LABELS)

    report(node, "正在拉取公司画像与申万行业归属…", phase="fetch_section")
    profile_stock, industry, profile_text = _fetch_profile_pack(code, name)
    if industry:
        industry_name = str(industry.get("name") or industry.get("l3_name") or "").strip()
        industry_code = str(industry.get("code") or industry.get("l3_code") or "").strip()
    if "未能" not in profile_text:
        sections["公司画像与行业归属"] = profile_text
        sources.append("申万行业归属")

    report(node, "正在拉取同业竞争对照（申万三级成分股）…", phase="fetch_section")
    peer_text = _fetch_peer_competition_table(code, name)
    if peer_text and "未能" not in peer_text and "无法" not in peer_text:
        sections["同业竞争对照"] = peer_text
        sources.append("申万三级同业对照")

    report(node, "正在拉取定期报告公告（交易所 + 巨潮）…", phase="fetch_section")
    periodic_by_kind = _collect_periodic_items(code, name)
    sections["定期报告"] = _format_periodic_catalog(periodic_by_kind, name, code)

    report(node, "正在拉取行业竞争相关公告（交易所 + 巨潮）…", phase="fetch_section")
    notice_items = _collect_competition_notices(code, name)
    notices_text = (
        f"### 行业竞争相关公告目录（{name} {code}，近 {DATA_LOOKBACK_DAYS} 天，{len(notice_items)} 条）\n"
        + _fmt_items(notice_items, limit=50)
    )
    if notice_items:
        sections["行业竞争相关公告"] = notices_text

    from agent.tools.notice_pdf import ingest_notice_pdfs, pick_latest_full_report, pick_notice_pdfs

    pdf_targets: list[dict[str, Any]] = []
    for items in periodic_by_kind.values():
        picked = pick_latest_full_report(items)
        if picked:
            pdf_targets.append(picked)
    pdf_targets.extend(pick_notice_pdfs(notice_items, already=pdf_targets, limit=6))

    if pdf_targets:
        report(
            node,
            f"正在下载并抽取 {len(pdf_targets)} 份公告 PDF 正文…",
            phase="fetch_pdf",
        )
        pdf_text = ingest_notice_pdfs(
            pdf_targets,
            code=code,
            progress=lambda msg: report(node, msg, phase="fetch_pdf"),
        )
        if pdf_text:
            sections["公告 PDF 正文"] = pdf_text
            sources.append("公告 PDF 正文（巨潮/交易所）")

    report(node, "正在拉取七网相关报道…", phase="fetch_section")
    press_text = _fetch_press_coverage(code, name)
    if "（无相关报道）" not in press_text and "（未能获取" not in press_text:
        sections["七网报道"] = press_text

    industry_label = industry_name or "所属行业"
    window_note = (
        f"> **主线范围**：{name}（{code}）· {industry_label} · 近 {DATA_LOOKBACK_DAYS} 天 · "
        f"信息来源：交易所、巨潮资讯、公告 PDF 正文、七家指定披露媒体、申万同业对照\n\n"
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
        "industry_name": industry_name,
        "industry_code": industry_code,
        "sections": sections,
        "text": text,
        "sources_used": sources,
        "errors": errors,
        "data_available": bool(sections),
    }


def fetch_web_competition_supplement(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    industry_name: str = "",
    progress_node: str = "ic_search",
) -> dict[str, Any]:
    """联网搜索补充：最新行业规模、竞争格局、产业链与政策动态。"""
    from agent.tools.progress import report
    from agent.tools.web_search import search_for_competition, web_search_status

    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    available, engine_hint = web_search_status()
    if not available:
        report(progress_node, engine_hint, phase="web_search_skip", status="done")
        return {
            "text": "",
            "engines": [],
            "used": False,
            "sources_used": [],
        }

    report(
        progress_node,
        f"联网补充检索（{engine_hint}）…",
        phase="web_search",
        status="running",
    )

    def _on_query(query: str) -> None:
        report(progress_node, f"检索：{query}", phase="web_search")

    text, engines = search_for_competition(
        name,
        industry_name=industry_name,
        stock_code=code,
        progress_cb=_on_query,
    )
    used = bool(text)
    if used:
        engine_label = "+".join(engines) if engines else engine_hint
        sources = [f"联网搜索（{engine_label}）"]
        report(
            progress_node,
            f"联网补充完成（{engine_label}）",
            phase="web_search_done",
            status="running",
        )
    else:
        report(
            progress_node,
            "联网搜索未返回有效结果，将仅依据官方披露撰写",
            phase="web_search_done",
            status="running",
            level="warn",
        )
        sources = []

    header = (
        f"> **补充范围**：{industry_name or name} 行业最新公开数据与竞争动态；"
        "数字与事实若与交易所/巨潮冲突，以官方披露为准。\n\n"
    )
    return {
        "text": (header + text) if text else "",
        "engines": engines,
        "used": used,
        "sources_used": sources,
    }


def _collect_risk_notices(
    code: str,
    name: str,
    *,
    days: int | None = None,
    limit: int = 55,
) -> list[dict[str, Any]]:
    window = days if days is not None else DATA_LOOKBACK_DAYS
    api = _import_backend()
    cninfo_pack = _safe_call(
        "巨潮公告",
        api["query_cninfo"],
        code,
        days=window,
        max_pages=8,
        limit=90,
    )
    exchange_pack = _safe_call(
        "交易所公告",
        api["query_exchange"],
        code,
        days=window,
        max_pages=8,
        limit=90,
    )
    return _filter_risk_notices(
        _merge_notice_items(cninfo_pack, exchange_pack),
        limit=limit,
    )


def _fetch_risk_press_coverage(
    code: str,
    name: str,
    *,
    days: int | None = None,
    limit_per_outlet: int = 12,
) -> str:
    """从七家指定披露媒体官网拉取风险/治理相关报道。"""
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
        filtered = _filter_risk_notices(rows, limit=limit_per_outlet)
        if not filtered:
            filtered = rows[:limit_per_outlet]
        total += len(filtered)
        blocks.append(f"#### {label}（{len(filtered)} 条）\n{_fmt_items(filtered, limit=limit_per_outlet)}")

    if not blocks:
        flat = pack.get("items") or []
        if flat:
            filtered = _filter_risk_notices(flat, limit=35)
            blocks.append(_fmt_items(filtered or flat[:35], limit=35))
            total = len(filtered or flat[:35])

    header = f"### 七网风险与治理相关报道（{name} {code}，近{window}天，共 {total} 条）\n"
    return header + ("\n\n".join(blocks) if blocks else "（无相关报道）")


def fetch_risk_reviewer_data(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    progress_node: str = "rr_fetch",
) -> dict[str, Any]:
    """采集指定公司投资风险与管理层质量评估资料。"""
    from agent.tools.progress import report

    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    node = progress_node
    sections: dict[str, str] = {}
    sources: list[str] = []
    errors: list[str] = []
    industry_name = ""
    industry_code = ""

    report(node, f"采集 {name} 近 {DATA_LOOKBACK_DAYS} 天风险与治理资料", phase="fetch_data", status="running")
    sources.extend(OFFICIAL_SOURCE_LABELS)

    report(node, "正在拉取公司画像与申万行业归属…", phase="fetch_section")
    profile_stock, industry, profile_text = _fetch_profile_pack(code, name)
    if industry:
        industry_name = str(industry.get("name") or industry.get("l3_name") or "").strip()
        industry_code = str(industry.get("code") or industry.get("l3_code") or "").strip()
    if "未能" not in profile_text:
        sections["公司画像与行业归属"] = profile_text
        sources.append("申万行业归属")

    report(node, "正在拉取定期报告公告（交易所 + 巨潮）…", phase="fetch_section")
    periodic_by_kind = _collect_periodic_items(code, name)
    sections["定期报告"] = _format_periodic_catalog(periodic_by_kind, name, code)

    report(node, "正在拉取风险与治理相关公告（交易所 + 巨潮）…", phase="fetch_section")
    notice_items = _collect_risk_notices(code, name)
    notices_text = (
        f"### 风险与治理相关公告目录（{name} {code}，近 {DATA_LOOKBACK_DAYS} 天，{len(notice_items)} 条）\n"
        + _fmt_items(notice_items, limit=55)
    )
    if notice_items:
        sections["风险与治理相关公告"] = notices_text

    from agent.tools.notice_pdf import ingest_risk_notice_pdfs, pick_latest_full_report, pick_notice_pdfs

    pdf_targets: list[dict[str, Any]] = []
    for items in periodic_by_kind.values():
        picked = pick_latest_full_report(items)
        if picked:
            pdf_targets.append(picked)
    pdf_targets.extend(pick_notice_pdfs(notice_items, already=pdf_targets, limit=8))

    if pdf_targets:
        report(
            node,
            f"正在下载并抽取 {len(pdf_targets)} 份公告 PDF 正文…",
            phase="fetch_pdf",
        )
        pdf_text = ingest_risk_notice_pdfs(
            pdf_targets,
            code=code,
            progress=lambda msg: report(node, msg, phase="fetch_pdf"),
        )
        if pdf_text:
            sections["公告 PDF 正文"] = pdf_text
            sources.append("公告 PDF 正文（巨潮/交易所）")

    report(node, "正在拉取七网相关报道…", phase="fetch_section")
    press_text = _fetch_risk_press_coverage(code, name)
    if "（无相关报道）" not in press_text and "（未能获取" not in press_text:
        sections["七网报道"] = press_text

    industry_label = industry_name or "所属行业"
    window_note = (
        f"> **主线范围**：{name}（{code}）· {industry_label} · 近 {DATA_LOOKBACK_DAYS} 天 · "
        f"信息来源：交易所、巨潮资讯、公告 PDF 正文、七家指定披露媒体\n\n"
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
        "industry_name": industry_name,
        "industry_code": industry_code,
        "sections": sections,
        "text": text,
        "sources_used": sources,
        "errors": errors,
        "data_available": bool(sections),
    }


def fetch_web_risk_supplement(
    company: str,
    stock: dict[str, str] | None = None,
    *,
    industry_name: str = "",
    progress_node: str = "rr_search",
) -> dict[str, Any]:
    """联网搜索补充：最新监管动态、管理层言论、行业政策。"""
    from agent.tools.progress import report
    from agent.tools.web_search import search_for_risk, web_search_status

    resolved = stock or resolve_company(company)
    code = resolved["code"]
    name = resolved["name"]
    available, engine_hint = web_search_status()
    if not available:
        report(progress_node, engine_hint, phase="web_search_skip", status="done")
        return {
            "text": "",
            "engines": [],
            "used": False,
            "sources_used": [],
        }

    report(
        progress_node,
        f"联网补充检索（{engine_hint}）…",
        phase="web_search",
        status="running",
    )

    def _on_query(query: str) -> None:
        report(progress_node, f"检索：{query}", phase="web_search")

    text, engines = search_for_risk(
        name,
        industry_name=industry_name,
        stock_code=code,
        progress_cb=_on_query,
    )
    used = bool(text)
    if used:
        engine_label = "+".join(engines) if engines else engine_hint
        sources = [f"联网搜索（{engine_label}）"]
        report(
            progress_node,
            f"联网补充完成（{engine_label}）",
            phase="web_search_done",
            status="running",
        )
    else:
        report(
            progress_node,
            "联网搜索未返回有效结果，将仅依据官方披露撰写",
            phase="web_search_done",
            status="running",
            level="warn",
        )
        sources = []

    header = (
        f"> **补充范围**：{name}（{code}）最新监管动态、管理层言论与行业政策；"
        "数字与事实若与交易所/巨潮冲突，以官方披露为准。\n\n"
    )
    return {
        "text": (header + text) if text else "",
        "engines": engines,
        "used": used,
        "sources_used": sources,
    }
