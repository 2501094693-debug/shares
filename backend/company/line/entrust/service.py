"""委托盘口编排：thsdk 优先，HQ depth 兜底。

``scope``：
- ``book``：买卖档位总量（五档）
- ``levels``：当日分价表
- ``all``：book + levels（默认）；有 L2 时附带 queues
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code

from company.line.entrust.models import empty_pack
from company.line.entrust import hq_source, thsdk_source

logger = logging.getLogger(__name__)


def fetch_entrust(
    code: str,
    *,
    scope: str = "all",
    depth: str = "5",
    source: str = "auto",
    force_hq: bool = False,
) -> dict[str, Any]:
    """拉取一只股票的委托盘口。

    - ``source=auto``：先 thsdk（需扫码会话），失败再 HQ 游客 depth
    - ``source=thsdk`` / ``hq``：强制指定通道
    - ``force_hq=True``：等价 ``source=hq``（仅 book）
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    want = (scope or "all").strip().lower()
    if want not in {"book", "levels", "all", "queue", "queues"}:
        raise ValueError("scope 须为 book | levels | all")
    if want in {"queue", "queues"}:
        want = "all"

    channel = (source or "auto").strip().lower()
    if force_hq:
        channel = "hq"
    if channel not in {"auto", "thsdk", "hq"}:
        raise ValueError("source 须为 auto | thsdk | hq")

    pack = empty_pack(norm)
    notes: list[str] = []
    sources: list[str] = []

    need_book = want in {"book", "all"}
    need_levels = want in {"levels", "all"}

    if need_book:
        book_pack = _load_book(norm, depth=depth, channel=channel)
        pack["book"] = book_pack.get("book") or pack["book"]
        pack["queues"] = book_pack.get("queues") or pack["queues"]
        pack["permissions"] = book_pack.get("permissions") or pack["permissions"]
        if book_pack.get("source"):
            sources.append(str(book_pack["source"]))
        notes.extend(book_pack.get("notes") or [])

    if need_levels and channel != "hq":
        try:
            level_pack = thsdk_source.fetch_price_levels(norm)
            pack["levels"] = level_pack.get("levels") or []
            if level_pack.get("source"):
                sources.append(str(level_pack["source"]))
            notes.extend(level_pack.get("notes") or [])
        except Exception as exc:  # noqa: BLE001
            logger.info("entrust levels skip %s: %s", norm, exc)
            notes.append(f"分价表不可用：{exc}")
    elif need_levels and channel == "hq":
        notes.append("HQ 通道无分价表，请改用 source=thsdk / auto")

    if not pack["queues"]["bid"] and not pack["queues"]["ask"]:
        perms = pack.get("permissions") or {}
        if perms and not (
            perms.get("a_stock_level2") or perms.get("a_stock_extended_level2")
        ):
            notes.append(
                "手机端能看到的「买卖队列 / 委托单细则」需要 A 股 Level-2；"
                "请用开通 L2 的同花顺账号扫码登录后再试"
            )

    pack["source"] = "+".join(dict.fromkeys(sources)) if sources else ""
    unique_notes: list[str] = []
    seen: set[str] = set()
    for note in notes:
        if note in seen:
            continue
        seen.add(note)
        unique_notes.append(note)
    pack["notes"] = unique_notes
    return pack


def _load_book(code: str, *, depth: str, channel: str) -> dict[str, Any]:
    errors: list[str] = []
    if channel in {"auto", "thsdk"}:
        try:
            return thsdk_source.fetch_order_book(code, depth=depth)
        except Exception as exc:  # noqa: BLE001
            logger.info("entrust thsdk book skip %s: %s", code, exc)
            errors.append(f"thsdk: {exc}")
            if channel == "thsdk":
                raise

    try:
        pack = hq_source.fetch_order_book(code)
        if errors:
            pack.setdefault("notes", []).append(
                "thsdk 不可用，已降级 HQ depth（" + "; ".join(errors) + "）"
            )
        return pack
    except Exception as exc:  # noqa: BLE001
        if channel == "hq":
            raise
        detail = list(errors)
        detail.append(f"hq: {exc}")
        raise RuntimeError(f"委托盘口拉取失败（thsdk / HQ 皆不可用）：{detail}") from exc
