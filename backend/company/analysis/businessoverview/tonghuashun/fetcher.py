"""同花顺 F10「经营分析」接口接入。

页面：
  https://basic.10jqka.com.cn/{code}/operate.html

两个 JSON 接口（均无需鉴权、非 JS 渲染，requests 直连即可）：
  ``product_index_query``  主营构成（分产品/行业/地区，多期，支持 yoy）
  ``history_end_date``     可用报告期列表

外加 SSR 在 HTML 里的文本块（**页面是 GBK 编码，必须按 gbk 解码**）：
  主营介绍 / 产品类型 / 产品名称 / 经营范围 / 董事会经营评述 / 主要客户及供应商

字段注意（均为实测结论，勿"顺手修正"）：
  * ``index_value`` 是**字符串**，需转 float；
  * ``account`` 是该分部占比，**0~1 小数**，不是百分数；
  * ``yoy`` 默认返回 null，必须显式传 ``yoy=1`` 才有同比；
  * ``analysis_type``：``product``按产品 / ``industry``按行业 / ``area``按地区；
  * 不传 ``date`` 即返回**全部历史期**（600990 达 45 期），无需逐期请求；
  * 三个维度各自的历史期数不同（product 45 / industry 19 / area 18），
    且 ``area`` 返回顺序是**升序**，不可假定降序，必须自行排序。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from company.news.platforms.tonghuashun._common import (
    f10_news_url,
    ths_market,
)
from core.codes import normalize_code, safe_str
from core.http import browser_get

logger = logging.getLogger(__name__)

SOURCE = "tonghuashun"
CHANNEL = "ths_operate"

BASE_HOST = "https://basic.10jqka.com.cn"
PRODUCT_INDEX_API = f"{BASE_HOST}/basicapi/operate/index/v1/product_index_query/"
HISTORY_API = f"{BASE_HOST}/basicapi/operate/index/v1/history_end_date/"
OPERATE_PAGE = f"{BASE_HOST}/{{code}}/operate.html"

# analysis_type → 维度名
ANALYSIS_DIM: dict[str, str] = {
    "product": "按产品",
    "industry": "按行业",
    "area": "按地区",
}

# 接口全部维度一次拿全
ALL_ANALYSIS = "product,industry,area"

# 维度别名 → 接口值
TYPE_ALIASES = {
    "1": "product", "product": "product", "产品": "product", "按产品": "product",
    "分产品": "product",
    "2": "industry", "industry": "industry", "行业": "industry", "按行业": "industry",
    "分行业": "industry",
    "3": "area", "region": "area", "area": "area", "地区": "area", "按地区": "area",
    "分地区": "area",
}

# 默认优先级：产品 > 行业 > 地区
TYPE_PRIORITY: tuple[str, ...] = ("product", "industry", "area")

_SENTINEL = -1e10
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[\s　]+")


def operate_page_url(code: str) -> str:
    stock = normalize_code(code) or safe_str(code)
    return f"{BASE_HOST}/{stock}/operate.html" if stock else BASE_HOST


def normalize_analysis_type(value: str | None) -> str:
    """维度别名归一，返回 product/industry/area；'' 表示自动选择。"""
    key = safe_str(value).strip().lower()
    if not key:
        return ""
    if key in TYPE_ALIASES:
        return TYPE_ALIASES[key]
    raise ValueError("analysis_type 须为 1(按产品) | 2(按行业) | 3(按地区)")


def _num(value: Any) -> float | None:
    """宽松转 float；空值/'-'/'--'/超大负哨兵一律视为缺失。"""
    if value in (None, "", "-", "--"):
        return None
    try:
        number = float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    if number <= _SENTINEL:
        return None
    return number


def _clean(text: str) -> str:
    """去标签 + 压缩空白（含全角空格）。"""
    return _WS_RE.sub(" ", _TAG_RE.sub("", safe_str(text))).strip()


def _headers(code: str) -> dict[str, str]:
    return {
        "Referer": operate_page_url(code),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


def _get_json(code: str, url: str, params: dict[str, Any]) -> dict[str, Any]:
    resp = browser_get(url, params=params, headers=_headers(code), timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        return {}
    if payload.get("status_code") not in (0, "0", None):
        raise ValueError(
            f"同花顺接口返回异常: {payload.get('status_msg') or payload.get('status_code')}"
        )
    return payload


# --------------------------------------------------------------------------
# 一、可用报告期 history_end_date
# --------------------------------------------------------------------------

def fetch_periods(code: str, *, analysis_types: str = ALL_ANALYSIS) -> list[str]:
    """可用报告期列表，降序。"""
    stock = normalize_code(code) or safe_str(code)
    market = ths_market(stock)
    if not stock:
        return []
    payload = _get_json(
        stock,
        HISTORY_API,
        {
            "code": stock,
            "market": market,
            "type": "stock",
            "analysisTypes": analysis_types,
        },
    )
    dates = [
        safe_str(row.get("date"))[:10]
        for row in (payload.get("data") or [])
        if isinstance(row, dict)
    ]
    return sorted({d for d in dates if d}, reverse=True)


# --------------------------------------------------------------------------
# 二、主营构成 product_index_query
# --------------------------------------------------------------------------

def _item(
    node: dict[str, Any],
    *,
    code: str,
    date: str,
    analysis_type: str,
) -> dict[str, Any] | None:
    name = safe_str(node.get("product_name"))
    if not name:
        return None

    # index_analysis_list: [{index_id, index_value, yoy, account}]
    values: dict[str, dict[str, Any]] = {}
    for row in node.get("index_analysis_list") or []:
        if not isinstance(row, dict):
            continue
        idx = safe_str(row.get("index_id"))
        if not idx:
            continue
        values[idx] = row

    income = values.get("income") or {}
    cost = values.get("cost") or {}
    profit = values.get("gross_profit") or {}
    margin = values.get("gross_profit_rate") or {}

    children = node.get("children") or []
    return {
        "code": code,
        "report_date": date,
        "dimension": ANALYSIS_DIM.get(analysis_type, "未知"),
        "dimension_key": analysis_type,
        "analysis_type": analysis_type,
        "item_name": name,
        "level": safe_str(node.get("level")) or "1",
        "level_code": safe_str(node.get("level_code")),
        # 金额单位：元
        "revenue": _num(income.get("index_value")),
        "revenue_ratio": _num(income.get("account")),          # 0~1
        "revenue_yoy": _num(income.get("yoy")),                # 需 yoy=1
        "cost": _num(cost.get("index_value")),
        "cost_ratio": _num(cost.get("account")),
        "gross_profit": _num(profit.get("index_value")),
        "gross_profit_ratio": _num(profit.get("account")),      # 0~1
        "gross_margin": _num(margin.get("index_value")),
        # 二级分部（level=2 且 child=1 时才有）
        "children": [
            c for c in (
                _item(x, code=code, date=date, analysis_type=analysis_type)
                for x in children if isinstance(x, dict)
            ) if c
        ],
        "sort_value": _num(node.get("sort_value")),
        "source": SOURCE,
        "channel": CHANNEL,
    }


def _period_block(
    block: dict[str, Any],
    *,
    code: str,
    analysis_type: str,
) -> dict[str, Any]:
    date = safe_str(block.get("time"))[:10]
    items = [
        item
        for item in (
            _item(node, code=code, date=date, analysis_type=analysis_type)
            for node in (block.get("product_index_item_list") or [])
            if isinstance(node, dict)
        )
        if item
    ]
    items.sort(key=lambda x: (x["revenue_ratio"] is None, -(x["revenue_ratio"] or 0.0)))

    totals = {}
    for row in block.get("index_total_list") or []:
        if isinstance(row, dict):
            idx = safe_str(row.get("index_id"))
            if idx:
                totals[idx] = {
                    "total": _num(row.get("index_total")),
                    "yoy": _num(row.get("index_total_yoy")),
                }

    return {
        "report_date": date,
        "items": items,
        "count": len(items),
        "total_ratio": sum(i["revenue_ratio"] or 0.0 for i in items),
        "totals": totals,
    }


def _segments_params(
    stock: str,
    *,
    with_yoy: bool,
    with_children: bool,
    date: str,
) -> dict[str, Any]:
    """主营构成接口参数（三个维度一次拿全）。"""
    params: dict[str, Any] = {
        "code": stock,
        "market": ths_market(stock),
        "type": "stock",
        "analysisTypes": ALL_ANALYSIS,
        "sortIndex": "income",
        "account": 1,
        "timeField": "date",
        "currency": "CNY",
        "level": 2 if with_children else 1,
        "expands": "product_introduction",
        "locale": "zh_CN",
        "reportTypes": 4,
    }
    if with_yoy:
        params["yoy"] = 1
    if with_children:
        params["child"] = 1
    if date:
        params["date"] = str(date)[:10]
    return params


def _parse_by_type(
    stock: str, blocks: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """把接口返回的 blocks 按 analysis_type 归并成「维度 → 按期降序的期列表」。

    各维度的期数不同（product 25 / industry 10 / area 10，实测），不能共用一个列表。
    """
    by_type: dict[str, list[dict[str, Any]]] = {}
    for blk in blocks:
        atype = safe_str(blk.get("analysis_type"))
        periods = [
            p
            for p in (
                _period_block(b, code=stock, analysis_type=atype)
                for b in (blk.get("time_operate_index_item_list") or [])
                if isinstance(b, dict)
            )
            if p.get("report_date")
        ]
        # 接口返回顺序不保证降序（area 实测为升序），统一自行排序
        periods.sort(key=lambda x: x["report_date"], reverse=True)
        if periods:
            by_type[atype] = periods
    return by_type


def _pack_from_periods(
    stock: str,
    by_type: dict[str, list[dict[str, Any]]],
    want: str,
    *,
    latest_n: int,
) -> dict[str, Any]:
    """由某一维度的期列表拼出该维度的 pack（结构同 :func:`fetch_operate_segments`）。"""
    periods = by_type.get(want) or []
    picked = periods[: max(1, int(latest_n))]
    all_dates = [p["report_date"] for p in periods]

    # segments 含全部选中期（供引擎按期拆分做结构对比），
    # 展示用 latest 期的 ``periods[0]["items"]``
    all_items: list[dict[str, Any]] = []
    for p in picked:
        all_items.extend(p["items"])

    return {
        "code": stock,
        "market": ths_market(stock),
        "source": SOURCE,
        "channel": CHANNEL,
        "dimension": ANALYSIS_DIM.get(want, ""),
        "analysis_type": want,
        "report_date": picked[0]["report_date"] if picked else "",
        "report_dates": [p["report_date"] for p in picked],
        "all_periods": all_dates,
        "period_count": len(periods),
        "count": picked[0]["count"] if picked else 0,
        "segments": all_items,
        "total_ratio": picked[0]["total_ratio"] if picked else 0.0,
        "totals": picked[0]["totals"] if picked else {},
        "periods": picked,
        "error": "",
        "page": operate_page_url(stock),
    }


def fetch_operate_dimensions(
    code: str,
    *,
    latest_n: int = 1,
    with_yoy: bool = True,
    with_children: bool = False,
) -> dict[str, dict[str, Any]]:
    """一次请求取全三个维度（product / industry / area）。

    ``product_index_query`` 本身就返回三个维度的数据块（``analysisTypes=ALL_ANALYSIS``），
    此处把全量暴露出来，避免为取三个维度发三次请求。

    返回 ``{"product": pack, "industry": pack, "area": pack}``；
    某维度该股无披露时，该键**不存在**（不返回空 pack）。
    每项 pack 的结构与 :func:`fetch_operate_segments` 完全一致。
    """
    stock = normalize_code(code) or safe_str(code)
    if not stock:
        raise ValueError("缺少股票代码")

    params = _segments_params(
        stock, with_yoy=with_yoy, with_children=with_children, date=""
    )
    payload = _get_json(stock, PRODUCT_INDEX_API, params)
    blocks = [b for b in (payload.get("data") or []) if isinstance(b, dict)]
    if not blocks:
        raise ValueError("同花顺主营构成为空")

    by_type = _parse_by_type(stock, blocks)
    if not by_type:
        raise ValueError("该股无任何维度的主营构成数据")

    return {
        want: _pack_from_periods(stock, by_type, want, latest_n=latest_n)
        for want in TYPE_PRIORITY
        if by_type.get(want)
    }


def fetch_operate_segments(
    code: str,
    *,
    latest_n: int = 1,
    analysis_type: str = "",
    with_yoy: bool = True,
    with_children: bool = False,
    date: str = "",
) -> dict[str, Any]:
    """主营构成。

    ``latest_n`` 取最近 N 个报告期（默认 1）。
    ``analysis_type`` 留空按 产品 > 行业 > 地区 自动选；否则 1/2/3 或英文/中文别名。
    ``with_children`` 是否带二级分部（level=2 & child=1）。
    ``date`` 指定报告期（如 '2025-12-31'），用于与另一数据源对齐口径。
    """
    stock = normalize_code(code) or safe_str(code)
    if not stock:
        raise ValueError("缺少股票代码")

    params = _segments_params(
        stock, with_yoy=with_yoy, with_children=with_children, date=date
    )
    payload = _get_json(stock, PRODUCT_INDEX_API, params)
    blocks = [b for b in (payload.get("data") or []) if isinstance(b, dict)]
    if not blocks:
        raise ValueError("同花顺主营构成为空")

    by_type = _parse_by_type(stock, blocks)

    want = normalize_analysis_type(analysis_type)
    if want and want not in by_type:
        # 显式指定的维度该股没有披露（如部分公司不披露分行业），回退到优先级
        fallback = next((t for t in TYPE_PRIORITY if by_type.get(t)), "")
        if not fallback:
            raise ValueError(f"该股无「{ANALYSIS_DIM.get(want, want)}」维度数据，且无其他可用维度")
        logger.info("同花顺 %s 无 %s 维度，回退到 %s", code, want, fallback)
        want = fallback
    elif not want:
        want = next((t for t in TYPE_PRIORITY if by_type.get(t)), "")
    if not want:
        raise ValueError("该股无任何维度的主营构成数据")

    return _pack_from_periods(stock, by_type, want, latest_n=latest_n)


def fetch_operate_all_dimensions(code: str, *, latest_n: int = 1) -> dict[str, str]:
    """三个维度各取最近一期，做交叉校验用。"""
    out: dict[str, str] = {}
    for atype in TYPE_PRIORITY:
        try:
            pack = fetch_operate_segments(code, latest_n=1, analysis_type=atype)
        except Exception as exc:  # noqa: BLE001
            logger.info("同花顺 %s 维度失败 %s: %s", atype, code, exc)
            continue
        out[atype] = pack["dimension"]
        if atype == TYPE_PRIORITY[0]:
            out["_first"] = pack.get("report_date", "")
    return out


# --------------------------------------------------------------------------
# 三、SSR 文本块（GBK 页面）
# --------------------------------------------------------------------------

# 标签 → 字段名
_INTRO_FIELDS: tuple[tuple[str, str], ...] = (
    ("主营业务：", "main_business"),
    ("产品类型：", "product_type"),
    ("产品名称：", "product_name"),
    ("经营范围：", "business_scope"),
)


def fetch_operate_page_text(code: str) -> str:
    """抓 SSR 页面 HTML。**同花顺 F10 页面是 GBK 编码**，必须按 gbk 解码。"""
    stock = normalize_code(code) or safe_str(code)
    if not stock:
        return ""
    resp = browser_get(operate_page_url(stock), headers=_headers(stock), timeout=20)
    resp.raise_for_status()
    for enc in ("gbk", "gb18030", "utf-8"):
        try:
            return resp.content.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return resp.content.decode("gb18030", errors="replace")


def _parse_intro(html: str) -> dict[str, Any]:
    """从 SSR HTML 解析主营介绍（主营业务 / 产品类型 / 产品名称 / 经营范围）。"""
    intro: dict[str, str] = {}
    for label, key in _INTRO_FIELDS:
        match = re.search(re.escape(label) + r"(.*?)</p>", html, re.S)
        intro[key] = _clean(match.group(1)) if match else ""

    # 产品名称是顿号分隔，拆成列表更便于与分部名对齐
    names = [n.strip() for n in re.split(r"[、,，]", intro.get("product_name", "")) if n.strip()]

    return {
        "main_business": intro.get("main_business", ""),
        "product_type": intro.get("product_type", ""),
        "product_name": intro.get("product_name", ""),
        "product_name_list": names,
        "business_scope": intro.get("business_scope", ""),
        "count": 1 if any(intro.values()) else 0,
        "error": "" if any(intro.values()) else "未抓到主营介绍（页面结构可能已变更）",
    }


def fetch_business_intro(code: str, *, html: str = "") -> dict[str, Any]:
    """主营介绍：主营业务 / 产品类型 / 产品名称 / 经营范围。

    ``html`` 非空时复用已抓取的页面，避免重复请求同一 URL。
    """
    stock = normalize_code(code) or safe_str(code)
    page = html or fetch_operate_page_text(stock)
    parsed = _parse_intro(page)

    return {
        "code": stock,
        "source": SOURCE,
        "channel": CHANNEL,
        "main_business": parsed["main_business"],
        "product_type": parsed["product_type"],
        "product_name": parsed["product_name"],
        "product_name_list": parsed["product_name_list"],
        "business_scope": parsed["business_scope"],
        "count": parsed["count"],
        "error": parsed["error"],
        "page": operate_page_url(stock),
    }


# 董事会经营评述：锚定正文区最后一个 <h2>董事会经营评述</h2>，
# 其后的 m_tab（各报告期链接 class="operateTab"）与
# m_tab_content 里的 <p class="f14 ... pr"> 即各期正文。
_REVIEW_HEAD_RE = re.compile(r"<h2[^>]*>\s*董事会经营评述\s*</h2>")
_REVIEW_TAB_RE = re.compile(r'<a[^>]*class="operateTab"[^>]*>(20\d{2}-\d{2}-\d{2})</a>')
_REVIEW_PARA_RE = re.compile(r'<p class="f14[^"]*pr"[^>]*>(.*?)</p>', re.S)


def _parse_review(html: str, *, limit: int = 4) -> dict[str, Any]:
    """从 SSR HTML 解析董事会经营评述各期正文。"""
    head = list(_REVIEW_HEAD_RE.finditer(html))
    if not head:
        return {
            "count": 0,
            "report_dates": [],
            "items": [],
            "review": "",
            "error": "未找到「董事会经营评述」区块（页面结构可能已变更）",
        }

    # 「董事会经营评述」在页面上会出现多次（导航链接 + 侧栏 + 正文标题），
    # 必须取最后一个 <h2> 作为区块起点，否则会抓到别的表格
    tail = html[head[-1].end():]
    # 评述区块在下一个 <h2> 标题处结束
    next_head = re.search(r"<h2[^>]*>", tail)
    section = tail[: next_head.start()] if next_head else tail

    dates = _REVIEW_TAB_RE.findall(section)
    # 正文 <p> 与报告期 <a> 在 DOM 上同序，实测一一对应
    paras = [_clean(p) for p in _REVIEW_PARA_RE.findall(section)]

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, date in enumerate(dates):
        if date in seen or i >= len(paras):
            continue
        text = paras[i]
        if len(text) < 200:
            continue
        seen.add(date)
        items.append(
            {
                "report_date": date,
                "review": text,
                "length": len(text),
                "truncated": i > 0,  # 页面首期为展开版，后续期是收起版（内容更短）
                "source": SOURCE,
                "channel": CHANNEL,
            }
        )
        if len(items) >= max(1, int(limit)):
            break

    return {
        "count": len(items),
        "report_dates": [i["report_date"] for i in items],
        "items": items,
        "review": items[0]["review"] if items else "",
        "error": "" if items else "未抓到经营评述（页面结构可能已变更）",
    }


def fetch_business_review(code: str, *, limit: int = 4, html: str = "") -> dict[str, Any]:
    """董事会经营评述（年报「管理层讨论与分析」原文段落）。

    SSR 页面结构：
      <h2>董事会经营评述</h2> → m_tab（各报告期链接 class="operateTab"）
      → m_tab_content（每期一个 <p class="f14 ... pr"> 正文）
    结构变更时返回空并在 ``error`` 说明，不做任何猜测。

    ``html`` 非空时复用已抓取的页面，避免重复请求同一 URL。
    """
    stock = normalize_code(code) or safe_str(code)
    page = html or fetch_operate_page_text(stock)
    parsed = _parse_review(page, limit=limit)

    items = [
        {"code": stock, **item} for item in parsed["items"]
    ]

    return {
        "code": stock,
        "source": SOURCE,
        "channel": CHANNEL,
        "count": parsed["count"],
        "report_dates": parsed["report_dates"],
        "items": items,
        "review": parsed["review"],
        "error": parsed["error"],
        "page": operate_page_url(stock),
    }


def fetch_operate_text_blocks(code: str, *, limit: int = 4) -> dict[str, Any]:
    """一次 SSR 页面抓取，同时取出主营介绍与董事会经营评述。

    页面 URL 相同，两块内容同源，合并为一次请求。
    """
    stock = normalize_code(code) or safe_str(code)
    html = fetch_operate_page_text(stock)
    intro = fetch_business_intro(stock, html=html)
    review = fetch_business_review(stock, limit=limit, html=html)
    return {"intro": intro, "review": review}


# --------------------------------------------------------------------------
# 四、一次性取全
# --------------------------------------------------------------------------

def fetch_operate_analysis(
    code: str,
    *,
    latest_n: int = 2,
    analysis_type: str = "",
    with_yoy: bool = True,
    with_intro: bool = True,
    with_review: bool = True,
    date: str = "",
) -> dict[str, Any]:
    """一个页面源取全：主营构成 + 主营介绍 + 经营评述。

    字段与 :mod:`company.analysis.businessoverview.core.normalize` 的统一契约对应。
    ``date`` 透传给 :func:`fetch_operate_segments`。
    """
    stock = normalize_code(code) or safe_str(code)
    out: dict[str, Any] = {
        "code": stock,
        "source": SOURCE,
        "channel": CHANNEL,
        "error": "",
        "page": operate_page_url(stock),
        "segments": [],
        "scope": "",
        "review": "",
    }

    try:
        pack = fetch_operate_segments(
            stock,
            latest_n=latest_n,
            analysis_type=analysis_type,
            with_yoy=with_yoy,
            date=date,
        )
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        pack = None

    if pack:
        out.update(
            {
                "market": pack["market"],
                "dimension": pack["dimension"],
                "analysis_type": pack["analysis_type"],
                "report_date": pack["report_date"],
                "report_dates": pack["report_dates"],
                "all_periods": pack["all_periods"],
                "period_count": pack["period_count"],
                "segments": pack["segments"],
                "total_ratio": pack["total_ratio"],
                "totals": pack["totals"],
                "periods": pack["periods"],
            }
        )

    if with_intro:
        try:
            intro = fetch_business_intro(stock)
            out.update(
                {
                    "main_business": intro["main_business"],
                    "product_type": intro["product_type"],
                    "product_name": intro["product_name"],
                    "product_name_list": intro["product_name_list"],
                }
            )
            # 同花顺「经营范围」比工商登记口径更贴主营，优先采用
            if intro["business_scope"]:
                out["scope"] = intro["business_scope"]
        except Exception as exc:  # noqa: BLE001
            logger.info("同花顺主营介绍失败 %s: %s", stock, exc)

    if with_review:
        try:
            review = fetch_business_review(stock)
            out.update(
                {
                    "review": review["review"],
                    "reviews": review["items"],
                    "review_dates": review["report_dates"],
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("同花顺经营评述失败 %s: %s", stock, exc)

    return out


def f10_home(code: str) -> str:
    """F10 入口页（与新闻平台保持一致的命名）。"""
    return f10_news_url(code) or operate_page_url(code)