"""编排：拉两路数据 → 3 秒窗口约束求解还原逐笔成交 → 汇总（对外主入口）。

    from company.analysis.deal import run_deal_window_reconstruct

    pack = run_deal_window_reconstruct("600519")
    pack["summary"]["order_lots"]      # 已归因到订单的成交手数
    pack["summary"]["small_lots"]      # 无归属小单手数
    pack["rows"][:5]                   # 逐笔：time/price/lots/buy_id/sell_id
"""

from __future__ import annotations

from typing import Any, Mapping

from core.codes import normalize_code

from company.analysis.deal.sources import load_big_deals, load_ticks
from company.analysis.deal.window import (
    DEFAULT_AVG_LOTS_PER_TICK,
    DEFAULT_MIN_LOTS,
    DEFAULT_TRADE_THRESHOLD,
    reconstruct_windows,
)


def run_deal_window_reconstruct(
    code: str,
    *,
    day: str = "",
    force: bool = False,
    threshold: float = DEFAULT_TRADE_THRESHOLD,
    min_lots: float = DEFAULT_MIN_LOTS,
    avg_lots_per_tick: float = DEFAULT_AVG_LOTS_PER_TICK,
    max_lookback: int = 0,
    view: str = "all",
    with_rows: bool = True,
    with_windows: bool = True,
) -> dict[str, Any]:
    """按 3 秒窗口做约束求解，还原当日逐笔成交并标注订单归属。

    把每个分时快照当成一个约束窗口，用「量守恒 / 笔数守恒 / 单笔金额上限 /
    订单时序」联立求解，输出一个**可行解**，并把每个窗口的可解性如实报出来。

    - ``threshold``：资金动向收录门槛（元），决定单笔成交额上限
    - ``view``：``all``（默认，主/被买卖全部纳入）/ ``aggressor`` /
      ``buy`` / ``sell`` / ``both``（同 ``all``）
    - ``max_lookback``：订单成交最多回溯多少个窗口，0 表示不限制
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    ticks_pack = load_ticks(norm, day=day, force=force)
    tick_items = [row for row in ticks_pack.get("items") or [] if isinstance(row, Mapping)]
    if not tick_items:
        raise ValueError(f"{norm} 无分时成交数据（{day or '当日'}），无法还原")

    big_pack, big_error = load_big_deals(norm, day=day, force=force)
    big_items = [row for row in big_pack.get("items") or [] if isinstance(row, Mapping)]

    pack = reconstruct_windows(
        tick_items,
        big_items,
        code=norm,
        day=str(day or ticks_pack.get("day") or big_pack.get("session_day") or ""),
        threshold=threshold,
        min_lots=min_lots,
        avg_lots_per_tick=avg_lots_per_tick,
        max_lookback=max_lookback,
        view=view,
        with_rows=with_rows,
        with_windows=with_windows,
    )
    pack["name"] = str(ticks_pack.get("name") or big_pack.get("name") or "")
    pack["sources"] = {
        "ticks": str(ticks_pack.get("source") or ""),
        "big_deal": str(big_pack.get("source") or ""),
        "ticks_rows": len(tick_items),
        "big_deal_rows": len(big_items),
        "big_deal_cached": bool(big_pack.get("cached")),
        "big_deal_day": str(big_pack.get("session_day") or ""),
        "last_time": ticks_pack.get("last_time"),
        "last_price": ticks_pack.get("last_price"),
    }
    if not big_items:
        pack.setdefault("notes", []).append(
            f"未取到大单明细（{big_error or '空'}），本次只能用分时成交自身推断"
        )
    return pack


def format_window_lines(pack: dict[str, Any]) -> list[str]:
    """把窗口级还原包压成几行文本。"""
    summary = pack.get("summary") or {}
    reconcile = pack.get("reconcile") or {}
    fills = pack.get("fills") or {}
    ambiguity = pack.get("ambiguity") or {}
    lines = [
        f"{pack.get('code')} {pack.get('name') or ''}  {pack.get('day') or ''}  "
        f"窗口 {summary.get('windows')}  订单 {summary.get('order_count')}  "
        f"还原成交 {pack.get('count')} 笔",
        f"  当日成交 {summary.get('lots')} 手 / {summary.get('count')} 笔",
        f"  订单成交 {summary.get('order_lots')} 手（占比 {summary.get('order_ratio')}%）"
        f" / {summary.get('order_count')} 笔",
        f"  无归属小单 {summary.get('small_lots')} 手 / {summary.get('small_count')} 笔",
        f"  每单拆成 {fills.get('mean')} 笔成交（中位 {fills.get('median')}，最多 {fills.get('max')}）",
        f"  核对：手数不符窗口 {reconcile.get('lot_mismatch_windows')}  "
        f"笔数不符窗口 {reconcile.get('count_mismatch_windows')}  "
        f"约束无解窗口 {reconcile.get('infeasible_windows')}  "
        f"未放置订单 {reconcile.get('unplaced_count')}",
        f"  解空间：{ambiguity.get('undetermined_windows')} 个窗口需猜测分配，"
        f"约 10^{ambiguity.get('solutions_log10')} 种可行解",
    ]
    for note in pack.get("notes") or []:
        lines.append(f"  注意：{note}")
    return lines


__all__ = [
    "DEFAULT_TRADE_THRESHOLD",
    "format_window_lines",
    "run_deal_window_reconstruct",
]
