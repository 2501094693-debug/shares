"""同花顺 HQ 大资金动向入口。"""

from __future__ import annotations

from typing import Any

from company.statistics.fundflow.tonghuashun.big_deal import fetch_big_deals


def get_fund_flow(
    code: str,
    *,
    scope: str = "big_deal",
    limit: int = 50,
    page: int = 1,
    order: str = "desc",
    force: bool = False,
    min_amount: float = 10_000_000,
    day: str = "",
    **_unused: Any,
) -> dict[str, Any]:
    """仅 ``scope=big_deal``。盘中覆盖磁盘缓存，盘后直接读文件。"""
    key = (scope or "big_deal").strip().lower()
    if key not in {"big_deal", "bigdeal", "ddzz", "tick", ""}:
        raise ValueError("同花顺资金流向仅支持 scope=big_deal")
    return fetch_big_deals(
        code,
        limit=int(limit or 0),
        page=page,
        order=order,
        min_amount=min_amount,
        force=force,
        day=day,
    )
