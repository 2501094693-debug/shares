"""散户情绪智能体 — 节点。"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.config import OPENAI_API_KEY, REPORTS_DIR
from agent.retail_sentiment.prompts import CLASSIFY_SYSTEM, build_classify_prompt, build_synthesis_prompt
from agent.retail_sentiment.rules import classify_text, is_retail_comment, needs_llm, user_key
from agent.retail_sentiment.state import RetailSentimentState
from agent.tools.data_fetcher import resolve_company
from agent.tools.progress import report as emit_progress
from agent.tools.retail_data import fetch_eastmoney, fetch_tonghuashun, fetch_xueqiu, safe_fetch
from agent.utils.llm import get_llm

logger = logging.getLogger(__name__)

_LLM_BATCH = 25
_LLM_MAX_ITEMS = 200
_STANCES = {"bull", "bear", "mixed", "unclear"}
_ACTIONS = {"buy", "sell", "wait", "none"}


def _kw(state: RetailSentimentState) -> dict[str, Any]:
    return {
        "days": int(state.get("days") or 3),
        "max_pages": int(state.get("max_pages") or 3),
        "with_replies": bool(state.get("with_replies") or False),
        "code": state.get("stock_code") or state.get("company") or "",
    }


def init_company(state: RetailSentimentState) -> dict:
    company = (state.get("company") or "").strip()
    emit_progress("rs_init", f"正在解析 {company}…", phase="resolve", status="running")
    stock = resolve_company(company)
    emit_progress("rs_init", f"已解析：{stock['name']} ({stock['code']})", phase="done", status="done")
    return {
        "data_cutoff_date": date.today().isoformat(),
        "stock_code": stock["code"],
        "stock_name": stock["name"],
        "stock_market": stock["market"],
        "days": int(state.get("days") or 3),
        "max_pages": int(state.get("max_pages") or 3),
        "with_replies": bool(state.get("with_replies") or False),
        "skip_llm": bool(state.get("skip_llm") or False),
        "errors": [],
        "sources_used": [],
    }


def _fetch_one(label: str, key: str, fn, state: RetailSentimentState) -> dict:
    kw = _kw(state)
    emit_progress(label, f"采集{key}评论…", phase="fetch_data", status="running")
    pack = safe_fetch(
        key,
        fn,
        kw["code"],
        days=kw["days"],
        max_pages=kw["max_pages"],
        with_replies=kw["with_replies"],
    )
    err = str(pack.get("error") or "")
    n = int(pack.get("count") or len(pack.get("items") or []))
    errors = [f"{key}: {err}"] if err else []
    sources = [key] if n or not err else []
    emit_progress(
        label,
        f"{key} {n} 条" + (f"（{err}）" if err else ""),
        phase="fetch_data_done",
        status="done",
    )
    return {f"raw_{key}": pack, "errors": errors, "sources_used": sources}


def fetch_em(state: RetailSentimentState) -> dict:
    return _fetch_one("rs_fetch_em", "eastmoney", fetch_eastmoney, state)


def fetch_ths(state: RetailSentimentState) -> dict:
    return _fetch_one("rs_fetch_ths", "tonghuashun", fetch_tonghuashun, state)


def fetch_xq(state: RetailSentimentState) -> dict:
    return _fetch_one("rs_fetch_xq", "xueqiu", fetch_xueqiu, state)


def _text_of(item: dict[str, Any]) -> str:
    parts = [item.get("title") or "", item.get("content") or "", item.get("summary") or ""]
    seen: list[str] = []
    for part in parts:
        text = str(part).strip()
        if text and text not in seen:
            seen.append(text)
    return "\n".join(seen).strip()


def _as_comment(source: str, item: dict[str, Any], *, role: str) -> dict[str, Any] | None:
    text = _text_of(item)
    if len(text) < 2:
        return None
    post_id = str(item.get("post_id") or item.get("article_id") or "")
    reply_id = str(item.get("reply_id") or "")
    cid = f"{source}:{post_id}:{reply_id or role}:{item.get('author_id') or item.get('author') or ''}"
    return {
        "id": cid,
        "source": source,
        "role": role,
        "post_id": post_id,
        "author": str(item.get("author") or ""),
        "author_id": str(item.get("author_id") or item.get("user_id") or ""),
        "text": text[:1500],
        "published_at": str(item.get("published_at") or ""),
        "url": str(item.get("url") or ""),
        "kind": str(item.get("kind") or ""),
        "channel": str(item.get("channel") or ""),
        "identity_tag": str(item.get("identity_tag") or item.get("user_tag") or ""),
        "followers_count": int(item.get("followers_count") or 0),
        "verified": bool(item.get("verified")),
        "media_name": str(item.get("media_name") or ""),
        "like_count": int(item.get("like_count") or 0),
    }


def _iter_items(pack: dict[str, Any]) -> list[dict[str, Any]]:
    posts = pack.get("posts") if isinstance(pack.get("posts"), dict) else {}
    items = posts.get("items") or pack.get("items") or []
    return [row for row in items if isinstance(row, dict)]


def _flatten(source: str, pack: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _iter_items(pack):
        comment = _as_comment(source, item, role="post")
        if comment:
            out.append(comment)
        for reply in item.get("replies") or []:
            if not isinstance(reply, dict):
                continue
            row = _as_comment(source, reply, role="reply")
            if row:
                out.append(row)
    return out


def _score_snap(pack: dict[str, Any]) -> dict[str, Any]:
    scores = pack.get("scores") if isinstance(pack.get("scores"), dict) else {}
    rank = pack.get("rank") if isinstance(pack.get("rank"), dict) else {}
    return {
        "error": str(pack.get("error") or scores.get("error") or ""),
        "count": int(pack.get("count") or 0),
        "total_score": scores.get("total_score"),
        "focus": scores.get("focus"),
        "org_participate": scores.get("org_participate"),
        "rank": rank.get("rank") or scores.get("rank"),
        "title": scores.get("title") or rank.get("title") or "",
    }


def merge_corpus(state: RetailSentimentState) -> dict:
    emit_progress("rs_merge", "合并三源评论…", phase="fetch_data", status="running")
    packs = {
        "eastmoney": state.get("raw_eastmoney") or {},
        "tonghuashun": state.get("raw_tonghuashun") or {},
        "xueqiu": state.get("raw_xueqiu") or {},
    }
    comments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, pack in packs.items():
        for row in _flatten(source, pack):
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            comments.append(row)
    emit_progress("rs_merge", f"合并后 {len(comments)} 条", phase="done", status="done")
    return {
        "comments": comments,
        "platform_scores": {k: _score_snap(v) for k, v in packs.items()},
    }


def filter_retail(state: RetailSentimentState) -> dict:
    emit_progress("rs_filter", "识别散户…", phase="fetch_data", status="running")
    kept: list[dict[str, Any]] = []
    for row in state.get("comments") or []:
        ok, reason = is_retail_comment(row)
        item = dict(row)
        item["is_retail"] = ok
        item["drop_reason"] = reason
        kept.append(item)
    n_retail = sum(1 for r in kept if r.get("is_retail"))
    emit_progress("rs_filter", f"散户语料 {n_retail}/{len(kept)}", phase="done", status="done")
    return {"comments": kept}


def _parse_labels(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return []
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return []
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    rows = payload.get("labels") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        stance = str(row.get("stance") or "unclear")
        action = str(row.get("action") or "none")
        out.append(
            {
                "id": str(row["id"]),
                "stance": stance if stance in _STANCES else "unclear",
                "action": action if action in _ACTIONS else "none",
                "confidence": float(row.get("confidence") or 0.5),
                "is_retail": bool(row.get("is_retail", True)),
                "via": "llm",
            }
        )
    return out


def _llm_relabel(state: RetailSentimentState, pending: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not pending or state.get("skip_llm") or not OPENAI_API_KEY:
        return {}
    llm = get_llm()
    merged: dict[str, dict[str, Any]] = {}
    for start in range(0, min(len(pending), _LLM_MAX_ITEMS), _LLM_BATCH):
        batch = pending[start : start + _LLM_BATCH]
        prompt = build_classify_prompt(
            state.get("stock_name") or "",
            state.get("stock_code") or "",
            batch,
        )
        try:
            resp = llm.invoke([SystemMessage(content=CLASSIFY_SYSTEM), HumanMessage(content=prompt)])
            content = getattr(resp, "content", None)
            if not isinstance(content, str):
                content = str(content or "")
            for lab in _parse_labels(content):
                merged[lab["id"]] = lab
        except Exception as exc:  # noqa: BLE001
            logger.warning("评论标注 LLM 失败: %s", exc)
            break
    return merged


def classify_comments(state: RetailSentimentState) -> dict:
    comments = [dict(row) for row in (state.get("comments") or [])]
    emit_progress("rs_classify", f"规则标注 {len(comments)} 条…", phase="llm", status="running")
    pending: list[dict[str, Any]] = []
    for row in comments:
        lab = classify_text(row.get("text") or "")
        row["stance"] = lab["stance"]
        row["action"] = lab["action"]
        row["confidence"] = lab["confidence"]
        row["via"] = lab["via"]
        if row.get("is_retail") and needs_llm(lab):
            pending.append(row)

    updates = _llm_relabel(state, pending)
    for row in comments:
        extra = updates.get(row["id"])
        if not extra:
            continue
        row["stance"] = extra["stance"]
        row["action"] = extra["action"]
        row["confidence"] = extra["confidence"]
        row["via"] = extra["via"]
        if extra.get("is_retail") is False:
            row["is_retail"] = False
            row["drop_reason"] = row.get("drop_reason") or "llm"

    labels = [
        {
            "id": r["id"],
            "source": r.get("source"),
            "user": user_key(r),
            "stance": r.get("stance"),
            "action": r.get("action"),
            "confidence": r.get("confidence"),
            "is_retail": r.get("is_retail"),
            "via": r.get("via"),
        }
        for r in comments
    ]
    emit_progress("rs_classify", f"标注完成，LLM 覆盖 {len(updates)} 条", phase="llm_done", status="done")
    return {"comments": comments, "labels": labels}


def _pick_latest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def key(row: dict[str, Any]) -> str:
        return str(row.get("published_at") or "")

    return sorted(rows, key=key)[-1]


def _count_block(users: dict[str, dict[str, Any]]) -> dict[str, Any]:
    n_users = len(users)
    stance_c = {"bull": 0, "bear": 0, "mixed": 0, "unclear": 0}
    action_c = {"buy": 0, "sell": 0, "wait": 0, "none": 0}
    for row in users.values():
        stance_c[str(row.get("stance") or "unclear")] = stance_c.get(str(row.get("stance") or "unclear"), 0) + 1
        action_c[str(row.get("action") or "none")] = action_c.get(str(row.get("action") or "none"), 0) + 1
    valid_stance = stance_c["bull"] + stance_c["bear"] + stance_c["mixed"]
    valid_action = action_c["buy"] + action_c["sell"] + action_c["wait"]
    return {
        "n_retail_users": n_users,
        "bull_users": stance_c["bull"],
        "bear_users": stance_c["bear"],
        "mixed_users": stance_c["mixed"],
        "unclear_users": stance_c["unclear"],
        "buy_users": action_c["buy"],
        "sell_users": action_c["sell"],
        "wait_users": action_c["wait"],
        "none_action_users": action_c["none"],
        "bull_share": round(stance_c["bull"] / valid_stance, 4) if valid_stance else None,
        "bear_share": round(stance_c["bear"] / valid_stance, 4) if valid_stance else None,
        "buy_share": round(action_c["buy"] / valid_action, 4) if valid_action else None,
        "sell_share": round(action_c["sell"] / valid_action, 4) if valid_action else None,
        "wait_share": round(action_c["wait"] / valid_action, 4) if valid_action else None,
    }


def aggregate(state: RetailSentimentState) -> dict:
    emit_progress("rs_agg", "按用户计数…", phase="llm", status="running")
    comments = state.get("comments") or []
    retail = [r for r in comments if r.get("is_retail")]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in retail:
        groups.setdefault(user_key(row), []).append(row)
    latest = {uid: _pick_latest(rows) for uid, rows in groups.items()}

    by_source: dict[str, dict[str, Any]] = {}
    for source in ("eastmoney", "tonghuashun", "xueqiu"):
        sub = {k: v for k, v in latest.items() if v.get("source") == source}
        block = _count_block(sub)
        block["n_comments"] = sum(1 for r in retail if r.get("source") == source)
        by_source[source] = block

    metrics = _count_block(latest)
    metrics["n_comments"] = len(comments)
    metrics["n_retail_comments"] = len(retail)
    metrics["n_users"] = len({user_key(r) for r in comments if user_key(r)})
    metrics["by_source"] = by_source
    emit_progress(
        "rs_agg",
        f"散户 {metrics['n_retail_users']} 人 · 买{metrics['buy_users']} 卖{metrics['sell_users']} 观望{metrics['wait_users']}",
        phase="done",
        status="done",
    )
    return {"metrics": metrics}


def _pct(value: float | None) -> str:
    if value is None:
        return "样本不足"
    return f"{value:.0%}"


def _template_narrative(state: RetailSentimentState) -> str:
    m = state.get("metrics") or {}
    name = state.get("stock_name") or ""
    code = state.get("stock_code") or ""
    days = int(state.get("days") or 3)
    n = int(m.get("n_retail_users") or 0)
    if n <= 0:
        return (
            f"{name}（{code}）近 {days} 天三源社区未识别出发声散户。"
            "可能是采集失败、窗口内无人讨论，或过滤后没有个人用户。不能据此判断市场情绪。"
        )
    lean = "多空接近"
    if (m.get("bull_users") or 0) > (m.get("bear_users") or 0) * 1.2:
        lean = "偏看多"
    elif (m.get("bear_users") or 0) > (m.get("bull_users") or 0) * 1.2:
        lean = "偏看空"
    src = m.get("by_source") or {}
    src_bits = []
    for key, label in (("eastmoney", "东财"), ("tonghuashun", "同花顺"), ("xueqiu", "雪球")):
        block = src.get(key) or {}
        src_bits.append(f"{label}{block.get('n_retail_users') or 0}人")
    return (
        f"{name}（{code}）近 {days} 天发声散户 {n} 人（按平台用户去重，跨平台可能重复）。"
        f"立场有效票里看多 {_pct(m.get('bull_share'))}、看空 {_pct(m.get('bear_share'))}，整体{lean}。"
        f"行动意图：买入 {m.get('buy_users') or 0}、卖出 {m.get('sell_users') or 0}、观望 {m.get('wait_users') or 0}。"
        f"分源人数：{' / '.join(src_bits)}。"
        "以上是评论样本估计，不是真实持仓或成交账户。"
    )


def synthesize(state: RetailSentimentState) -> dict:
    emit_progress("rs_synth", "生成解读…", phase="llm", status="running")
    fallback = _template_narrative(state)
    narrative = fallback
    if not state.get("skip_llm") and OPENAI_API_KEY:
        try:
            llm = get_llm()
            prompt = build_synthesis_prompt(
                state.get("stock_name") or "",
                state.get("stock_code") or "",
                int(state.get("days") or 3),
                state.get("metrics") or {},
                state.get("platform_scores") or {},
            )
            resp = llm.invoke(
                [
                    SystemMessage(content="你是A股社区情绪分析助手。只描述样本，不给投资建议。"),
                    HumanMessage(content=prompt),
                ]
            )
            text = getattr(resp, "content", None)
            if isinstance(text, str) and len(text.strip()) > 40:
                narrative = text.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("情绪解读 LLM 失败: %s", exc)
            narrative = fallback

    m = state.get("metrics") or {}
    errors = state.get("errors") or []
    scores = state.get("platform_scores") or {}
    lines = [
        f"# {state.get('stock_name') or ''}（{state.get('stock_code') or ''}）发声散户情绪",
        "",
        f"- 窗口：近 {state.get('days') or 3} 天 · 截止日期 {state.get('data_cutoff_date') or ''}",
        f"- 口径：一人一票（取该用户窗口内最新一条）；跨平台不去重真人",
        f"- 散户人数：{m.get('n_retail_users') or 0}（评论 {m.get('n_retail_comments') or 0} 条 / 采集 {m.get('n_comments') or 0} 条）",
        f"- 看多 {m.get('bull_users') or 0} · 看空 {m.get('bear_users') or 0} · 矛盾 {m.get('mixed_users') or 0}",
        f"- 买入 {m.get('buy_users') or 0} · 卖出 {m.get('sell_users') or 0} · 观望 {m.get('wait_users') or 0}",
        "",
        "## 解读",
        "",
        narrative,
        "",
        "## 分源",
        "",
    ]
    by_source = m.get("by_source") or {}
    for key, title in (("eastmoney", "东方财富"), ("tonghuashun", "同花顺"), ("xueqiu", "雪球")):
        block = by_source.get(key) or {}
        snap = scores.get(key) or {}
        lines.append(
            f"- {title}：散户 {block.get('n_retail_users') or 0} 人，"
            f"买 {block.get('buy_users') or 0} / 卖 {block.get('sell_users') or 0} / 观望 {block.get('wait_users') or 0}"
            f"；平台快照 {snap.get('title') or '无'}"
        )
    if errors:
        lines.extend(["", "## 采集问题", ""])
        lines.extend(f"- {e}" for e in errors)
    lines.extend(
        [
            "",
            "## 限制",
            "",
            "- 发帖的是爱说话的少数人，不能外推到全体散户",
            "- 买入/卖出是文本意图，不是成交",
            "- 来源：东方财富股吧、同花顺讨论、雪球讨论（现有 company.emotion 采集）",
            "",
        ]
    )
    report = "\n".join(lines)
    emit_progress("rs_synth", "解读完成", phase="llm_done", status="done")
    return {"narrative": narrative, "report": report}


def save_report(state: RetailSentimentState) -> dict:
    company = state.get("company") or ""
    cutoff = (state.get("data_cutoff_date") or date.today().isoformat()).replace("-", "")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", state.get("stock_name") or company)
    code = state.get("stock_code") or ""
    stem = f"{safe_name}_{code}" if code and code not in safe_name else safe_name
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{stem}发声散户情绪_{cutoff}.md"
    emit_progress("rs_save", "正在保存报告…", phase="save_file", status="running")
    path.write_text(state.get("report") or "", encoding="utf-8")
    emit_progress("rs_save", f"已保存至 {path.name}", phase="done", status="done")
    return {"report_path": str(path)}
