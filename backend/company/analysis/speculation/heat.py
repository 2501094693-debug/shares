"""三源热度：排名序列 + 每日帖/回复量。"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Callable

from core.fmt import to_float

from company.emotion.eastmoney.posts import fetch_posts as em_fetch_posts
from company.emotion.eastmoney.rank import fetch_rank as em_fetch_rank
from company.emotion.tonghuashun.posts import fetch_posts as ths_fetch_posts
from company.emotion.tonghuashun.rank import fetch_rank as ths_fetch_rank
from company.emotion.xueqiu.posts import fetch_posts as xq_fetch_posts
from company.emotion.xueqiu.rank import fetch_rank as xq_fetch_rank

logger = logging.getLogger(__name__)

HEAT_DAYS = 10
_POST_MAX_PAGES = 8


def _day_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10] if len(text) >= 10 else ""


def _last_n_days(n: int = HEAT_DAYS) -> list[str]:
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _bucket_daily(items: list[dict[str, Any]], *, days: int = HEAT_DAYS) -> list[dict[str, Any]]:
    """按日聚合：帖数 + 回复数（用帖内 comment_count）+ 合计。"""
    wanted = set(_last_n_days(days))
    posts: dict[str, int] = defaultdict(int)
    replies: dict[str, int] = defaultdict(int)
    for item in items:
        if not isinstance(item, dict):
            continue
        day = _day_key(item.get("published_at"))
        if not day or day not in wanted:
            continue
        posts[day] += 1
        replies[day] += int(to_float(item.get("comment_count")) or 0)
    out: list[dict[str, Any]] = []
    for day in _last_n_days(days):
        post_n = posts.get(day, 0)
        reply_n = replies.get(day, 0)
        out.append(
            {
                "date": day,
                "post_count": post_n,
                "reply_count": reply_n,
                "comment_total": post_n + reply_n,
            }
        )
    return out


def _safe_posts(fetcher: Callable[..., dict[str, Any]], code: str, *, sort: str = "time") -> dict[str, Any]:
    try:
        return fetcher(
            code,
            sort=sort,
            days=HEAT_DAYS,
            max_pages=_POST_MAX_PAGES,
            with_replies=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("炒作热度帖子失败 %s: %s", code, exc)
        return {"items": [], "error": str(exc)}


def _em_ranks(code: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pack = em_fetch_rank(code)
    history = pack.get("history") if isinstance(pack.get("history"), list) else []
    ranks: list[dict[str, Any]] = []
    for row in history[-HEAT_DAYS:]:
        if not isinstance(row, dict):
            continue
        day = _day_key(row.get("calcTime"))
        rank_n = int(to_float(row.get("rank")) or 0)
        if not day:
            continue
        ranks.append({"date": day, "rank": rank_n or None})
    current = {
        "date": ranks[-1]["date"] if ranks else date.today().isoformat(),
        "rank": int(to_float(pack.get("rank")) or 0) or (ranks[-1]["rank"] if ranks else None),
        "history_available": True,
    }
    return ranks, current


def _ths_current(code: str) -> dict[str, Any]:
    pack = ths_fetch_rank(code)
    rank_n = int(to_float(pack.get("rank")) or 0)
    return {
        "date": date.today().isoformat(),
        "rank": rank_n or None,
        "heat": int(to_float(pack.get("heat")) or 0) or None,
        "rank_change": int(to_float(pack.get("rank_change")) or 0)
        if pack.get("rank_change") is not None
        else None,
        "history_available": False,
        "title": pack.get("title") or "",
        "error": pack.get("error") or "",
    }


def _xq_current(code: str) -> dict[str, Any]:
    pack = xq_fetch_rank(code)
    rank_n = int(to_float(pack.get("rank")) or 0)
    return {
        "date": date.today().isoformat(),
        "rank": rank_n or None,
        "value": pack.get("value"),
        "rank_change": pack.get("rank_change"),
        "history_available": False,
        "title": pack.get("title") or "",
        "error": pack.get("error") or "",
        "listed": bool(rank_n),
    }


def build_heat(code: str) -> dict[str, Any]:
    """东财：十日排名 + 十日帖/评；同花顺/雪球：今日排名 + 十日帖/评。"""
    em_ranks: list[dict[str, Any]] = []
    em_current: dict[str, Any] = {"history_available": True}
    ths_current: dict[str, Any] = {"history_available": False}
    xq_current: dict[str, Any] = {"history_available": False}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(_em_ranks, code): "em_rank",
            pool.submit(_ths_current, code): "ths_rank",
            pool.submit(_xq_current, code): "xq_rank",
            pool.submit(_safe_posts, em_fetch_posts, code, sort="time"): "em_posts",
            pool.submit(_safe_posts, ths_fetch_posts, code, sort="time"): "ths_posts",
            pool.submit(_safe_posts, xq_fetch_posts, code, sort="time"): "xq_posts",
        }
        results: dict[str, Any] = {}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("炒作热度任务失败 %s %s: %s", code, key, exc)
                errors[key] = str(exc)

    if "em_rank" in results:
        em_ranks, em_current = results["em_rank"]
    if "ths_rank" in results:
        ths_current = results["ths_rank"]
    if "xq_rank" in results:
        xq_current = results["xq_rank"]

    em_pack = results.get("em_posts") or {}
    ths_pack = results.get("ths_posts") or {}
    xq_pack = results.get("xq_posts") or {}
    if em_pack.get("error"):
        errors["em_posts"] = str(em_pack["error"])
    if ths_pack.get("error"):
        errors["ths_posts"] = str(ths_pack["error"])
    if xq_pack.get("error"):
        errors["xq_posts"] = str(xq_pack["error"])

    return {
        "days": HEAT_DAYS,
        "note": "东财含近十日排名；同花顺/雪球暂仅今日。每日评论量 = 主帖数 + 帖内回复数。",
        "eastmoney": {
            "label": "东方财富",
            "current": em_current,
            "ranks": em_ranks,
            "daily": _bucket_daily(list(em_pack.get("items") or [])),
        },
        "tonghuashun": {
            "label": "同花顺",
            "current": ths_current,
            "ranks": [],
            "daily": _bucket_daily(list(ths_pack.get("items") or [])),
        },
        "xueqiu": {
            "label": "雪球",
            "current": xq_current,
            "ranks": [],
            "daily": _bucket_daily(list(xq_pack.get("items") or [])),
        },
        "errors": errors,
    }
