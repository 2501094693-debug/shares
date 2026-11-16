"""大单资金动向统计：复用同花顺当日缓存，门槛过滤后做四象限汇总 + 分箱。

取数与列表接口 ``fetch_big_deals`` 同一份缓存、同一个 ``min_amount`` / ``day``
口径，因此汇总口径与页面列表完全一致，不会出现「列表 5 条、汇总 40 笔」。
"""

from __future__ import annotations

from typing import Any

from core.codes import normalize_code

from company.analysis.deal.fundflow.core import aggregate_big_deals, normalize_bin_by
from company.statistics.fundflow.tonghuashun.store import get_session_orders

DEFAULT_MIN_AMOUNT = 10_000_000


def fetch_big_deal_stats(
    code: str,
    *,
    min_amount: float = DEFAULT_MIN_AMOUNT,
    bin_by: str = "amount",
    force: bool = False,
    day: str = "",
) -> dict[str, Any]:
    """个股大单统计：四象限笔数/金额/手数 + 定步长分箱 + 净值。

    ``bin_by=amount``（默认）只出金额分箱，``lots`` 只出手数分箱，
    ``both`` 两套都出。历史 ``day`` 无缓存时返回空统计，不打 HQ。
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    mode = normalize_bin_by(bin_by)
    floor_amount = max(float(min_amount or 0.0), 0.0)

    session = get_session_orders(norm, force=force, day=day)
    items = [row for row in session.get("items") or [] if isinstance(row, dict)]
    stats = aggregate_big_deals(items, min_amount=floor_amount, bin_by=mode)

    return {
        "code": norm,
        "name": "",
        "scope": "big_deal_stats",
        "source": "tonghuashun" if items else "",
        "session_day": str(session.get("session_day") or ""),
        "cached": bool(session.get("cached")),
        "cached_at": str(session.get("cached_at") or ""),
        "min_amount": floor_amount,
        **stats,
        "note": str(session.get("note") or "同花顺 HQ 个股大单（主/被）"),
    }