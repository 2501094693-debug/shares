"""检索方式的形式化描述。

统一模板（每条子查询 arity 相同）：

    Qi := 源 ∧ 语料 ∧ 通道 ∧ 分类 ∧ 标题关键词 ∧ 窗口

槽位取值：
    源          = 巨潮资讯
    语料        = 非定期公告
    通道        = 全文 | 持续督导 | 投资者关系 | …
    分类        = ∈{…} | 任意
    标题关键词  = ∈{…} | 任意   （标题命中任一关键词，客户端 OR 匹配）
    窗口        = ≤N天

维内展示：

    本维 := 分组[Q1, Q2, …, Qn]   （组内去重，不跨组合并）

巨潮 searchkey 不支持 ``|`` 或运算，关键词一律在客户端按标题做 OR 匹配。

全部由 RiskQuery 参数生成，禁止手写散文。
"""
from __future__ import annotations

from typing import Any

from company.news.official.cninfo.constants import TAB_LABELS

from .taxonomy import RiskQuery, keyword_terms

SCHEMA = "risk-search/v1"
SOURCE = "巨潮资讯"
CORPUS = "非定期公告"
API = "fetch_announcements"
COMBINE = "by_query"
COMBINE_LABEL = "按子查询分组展示"

# 固定槽位顺序（展示与表达式共用）
SLOTS: tuple[str, ...] = ("源", "语料", "通道", "分类", "标题关键词", "窗口")

_TAB_CN: dict[str, str] = {
    "fulltext": "全文",
    "supervise": "持续督导",
    "relation": "投资者关系",
}

_ANY = "任意"


def _tab_label(tab: str) -> str:
    key = (tab or "fulltext").strip() or "fulltext"
    return _TAB_CN.get(key) or TAB_LABELS.get(key) or key


def _keyword_terms(keyword: str) -> list[str]:
    return keyword_terms(keyword)


def _fmt_set(values: list[str]) -> str:
    return "{" + ", ".join(values) + "}"


def _slot_atoms(q: RiskQuery) -> list[dict[str, Any]]:
    """固定 6 槽；无约束写「任意」，保证每条 Qi 形式一致。"""
    tab = (q.tab or "fulltext").strip() or "fulltext"
    cats = list(q.category or [])
    terms = _keyword_terms(q.keyword)
    days = int(q.days)

    return [
        {
            "slot": "源",
            "op": "eq",
            "value": SOURCE,
            "constrained": True,
            "text": f"源={SOURCE}",
        },
        {
            "slot": "语料",
            "op": "eq",
            "value": CORPUS,
            "constrained": True,
            "text": f"语料={CORPUS}",
        },
        {
            "slot": "通道",
            "op": "tab_eq",
            "value": tab,
            "label": _tab_label(tab),
            "constrained": True,
            "text": f"通道={_tab_label(tab)}",
        },
        {
            "slot": "分类",
            "op": "category_in" if cats else "any",
            "value": cats,
            "constrained": bool(cats),
            "text": f"分类∈{_fmt_set(cats)}" if cats else f"分类={_ANY}",
        },
        {
            "slot": "标题关键词",
            "op": "title_keyword_any" if terms else "any",
            "value": terms,
            "constrained": bool(terms),
            "text": f"标题关键词∈{_fmt_set(terms)}" if terms else f"标题关键词={_ANY}",
        },
        {
            "slot": "窗口",
            "op": "window_days",
            "value": days,
            "constrained": True,
            "text": f"窗口≤{days}天",
        },
    ]


def clause_expr(atoms: list[dict[str, Any]]) -> str:
    return " ∧ ".join(str(a["text"]) for a in atoms)


def build_clause(q: RiskQuery, index: int = 1) -> dict[str, Any]:
    """单条子查询：固定槽位 + 合取表达式。"""
    atoms = _slot_atoms(q)
    tab = (q.tab or "fulltext").strip() or "fulltext"
    cats = list(q.category or [])
    terms = _keyword_terms(q.keyword)
    return {
        "index": index,
        "qid": q.qid,
        "label": q.title,
        "symbol": f"Q{index}",
        "tab": tab,
        "tab_label": _tab_label(tab),
        "category": cats,
        "keyword": q.keyword or "",
        "keyword_terms": terms,
        "days": int(q.days),
        "slots": atoms,
        "filters": [a for a in atoms if a.get("constrained")],
        "expr": clause_expr(atoms),
        "method": "；".join(str(a["text"]) for a in atoms),
    }


def _clause_plain(c: dict[str, Any]) -> str:
    """单条查询的直白说明。"""
    channel = c.get("tab_label") or c.get("tab") or "全文"
    cats = list(c.get("category") or [])
    terms = list(c.get("keyword_terms") or [])
    days = c.get("days")
    parts: list[str] = [f"在「{channel}」通道"]
    if cats:
        parts.append("按分类「" + "、".join(cats) + "」筛选")
    if terms:
        shown = terms if len(terms) <= 8 else terms[:8]
        tail = "等" if len(terms) > 8 else ""
        parts.append("标题含「" + "、".join(shown) + tail + "」任一关键词")
    if not cats and not terms:
        parts.append("不额外限分类或标题词")
    parts.append(f"只取近 {days} 天")
    return "；".join(parts) + "。"


def format_search_method_plain(clauses: list[dict[str, Any]]) -> str:
    """维度级直白说明：给前端表格下方阅读。"""
    if not clauses:
        return f"本维暂无子查询。数据来自{SOURCE}的{CORPUS}。"
    n = len(clauses)
    details = "；".join(
        f"{c.get('symbol')}（{c.get('label')}）" + _clause_plain(c).rstrip("。")
        for c in clauses
    )
    return (
        f"本维从{SOURCE}的{CORPUS}里用 {n} 条规则检索："
        f"{details}。"
        f"结果按子查询分组列出；组内去重后按发布时间从新到旧排列。"
    )


def build_search_method(queries: list[RiskQuery]) -> dict[str, Any]:
    """维度级检索方式：统一 schema。"""
    clauses = [build_clause(q, i) for i, q in enumerate(queries, 1)]
    symbols = [c["symbol"] for c in clauses]
    if not symbols:
        dim_expr = "本维 := ∅"
    elif len(symbols) == 1:
        dim_expr = f"本维 := 分组[{symbols[0]}]"
    else:
        dim_expr = "本维 := 分组[" + ", ".join(symbols) + "]"

    template = "Qi := " + " ∧ ".join(SLOTS)
    plain = format_search_method_plain(clauses)

    return {
        "schema": SCHEMA,
        "template": template,
        "slots": list(SLOTS),
        "source": SOURCE,
        "corpus": CORPUS,
        "api": API,
        "combine": COMBINE,
        "combine_label": COMBINE_LABEL,
        "clauses": clauses,
        "dim_expr": dim_expr,
        "plain": plain,
        "text": format_search_method_text(
            {
                "template": template,
                "source": SOURCE,
                "corpus": CORPUS,
                "api": API,
                "combine_label": COMBINE_LABEL,
                "clauses": clauses,
                "dim_expr": dim_expr,
                "plain": plain,
            }
        ),
    }


def format_search_method_text(spec: dict[str, Any]) -> str:
    """形式化结构 → 纯文本（markdown / 日志）。优先输出直白说明。"""
    plain = str(spec.get("plain") or "").strip()
    if plain:
        return plain
    lines = [
        f"数据源：{spec.get('source')}/{spec.get('corpus')}",
        f"维内合并：{spec.get('combine_label') or COMBINE_LABEL}",
        "",
    ]
    for c in spec.get("clauses") or []:
        lines.append(f"{c.get('symbol')}. {c.get('label')}（{c.get('qid')}）")
        lines.append(f"  {c.get('expr')}")
    lines.append("")
    lines.append(str(spec.get("dim_expr") or ""))
    return "\n".join(lines).strip()


def describe_query_method(q: RiskQuery) -> str:
    """单条查询短描述（表格兼容）。"""
    return build_clause(q).get("method") or ""
