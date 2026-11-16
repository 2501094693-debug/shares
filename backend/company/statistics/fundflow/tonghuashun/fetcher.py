"""同花顺资金流向入口：HQ 大单 + thsdk 当日资金流拆分。"""

from __future__ import annotations

from typing import Any

from company.statistics.fundflow.tonghuashun.big_deal import fetch_big_deals
from company.statistics.fundflow.tonghuashun.daily_capital import fetch_daily_capital

_BIG_DEAL_SCOPES = {"big_deal", "bigdeal", "ddzz", "tick", ""}
_CAPITAL_SCOPES = {
    "daily_capital",
    "capital",
    "capital_flow",
    "capital_flows",
    "ths_capital",
}


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
    """``scope=big_deal|daily_capital``。

    - ``big_deal``：HQ 逐笔大单（盘中覆盖磁盘缓存，盘后读文件）
    - ``daily_capital``：thsdk 当日主动/被动 × 档位资金流快照（需扫码）
    """
    key = (scope or "big_deal").strip().lower()
    if key in _CAPITAL_SCOPES:
        return fetch_daily_capital(code)
    if key not in _BIG_DEAL_SCOPES:
        raise ValueError("同花顺资金流向仅支持 scope=big_deal | daily_capital")
    return fetch_big_deals(
        code,
        limit=int(limit or 0),
        page=page,
        order=order,
        min_amount=min_amount,
        force=force,
        day=day,
    )
