"""聪明投机者：首日低价买入，其后每日高卖低买（量=当日成交量×比例）。

规则（成交量统一换算为「股」后再按比例下单）::

    首日：在最低价买入 当日成交量 × ratio
    其后每个交易日：
      1. 在最高价卖出 min(当日成交量 × ratio, 当前持仓)
      2. 在最低价买入 当日成交量 × ratio

持仓成本两套口径并行维护::

    加权均价 avg_price
      买：cost += 价×量；卖：cost -= 当时均价×量；avg = cost / 股数
    净成本 net_avg_price
      买：net_cost += 价×量；卖：net_cost -= 卖出价×量；net_avg = net_cost / 股数

日线 ``volume`` 口径与 ``company.line.fetcher`` 一致：单位为「手」（1 手 = 100 股）。
"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float

# 默认：成交量的百分之一
DEFAULT_RATIO = 0.01
# fetcher 统一为「手」
SHARES_PER_LOT = 100.0


def _iso(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 8:
        raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or bar.get("date") or "")[:10]


def _volume_shares(bar: dict[str, Any]) -> float:
    """当日成交量（股）。``volume`` 为手时 ×100；若已给 ``volume_shares`` 则直接用。"""
    raw = to_float(bar.get("volume_shares"))
    if raw is not None and raw > 0:
        return float(raw)
    lots = to_float(bar.get("volume")) or 0.0
    return float(lots) * SHARES_PER_LOT


def _slice_bars(
    bars: list[dict[str, Any]],
    beg: str,
    end: str = "",
) -> list[dict[str, Any]]:
    beg_iso = _iso(beg)
    end_iso = _iso(end) if end else "9999-12-31"
    if beg_iso > end_iso:
        raise ValueError(f"起始日不能晚于结束日: {beg_iso} > {end_iso}")
    out: list[dict[str, Any]] = []
    for bar in sorted(bars, key=_bar_date):
        d = _bar_date(bar)
        if not d or d < beg_iso or d > end_iso:
            continue
        out.append(bar)
    if not out:
        raise ValueError(f"区间 [{beg_iso}, {end_iso if end else '最新'}] 无交易日")
    return out


def compute_trader(
    bars: list[dict[str, Any]],
    beg: str,
    end: str = "",
    *,
    ratio: float = DEFAULT_RATIO,
    return_history: bool = False,
) -> dict[str, Any]:
    """在已排序日线序列上模拟投机者，返回期末持仓股数与平均成本（纯函数）。

    - ``beg`` / ``end``：``YYYY-MM-DD`` 或 ``YYYYMMDD``；``end`` 空则用序列最后一根
    - 若 ``beg`` 非交易日，取区间内第一个交易日作为首日（仅买入）
    """
    if ratio <= 0 or ratio > 1:
        raise ValueError(f"ratio 须在 (0, 1]，收到 {ratio!r}")

    ordered = _slice_bars(bars, beg, end)
    beg_iso = _iso(beg)

    shares = 0.0
    cost = 0.0  # 加权：剩余持仓总成本（卖出按当时均价扣减）
    net_cost = 0.0  # 净成本：买入 +价×量，卖出 −卖出价×量
    bought = 0.0
    sold = 0.0
    sell_proceeds = 0.0
    realized_pnl = 0.0  # 已实现：卖出价相对当时加权均价
    history: list[dict[str, Any]] = []
    last_close: float | None = None

    for i, bar in enumerate(ordered):
        d = _bar_date(bar)
        high = to_float(bar.get("high"))
        low = to_float(bar.get("low"))
        close = to_float(bar.get("close"))
        vol = _volume_shares(bar)
        if high is None or low is None or high <= 0 or low <= 0:
            raise ValueError(f"{d} 最高/最低价无效")
        if vol < 0:
            raise ValueError(f"{d} 成交量无效")
        if close is not None and close > 0:
            last_close = float(close)

        target = vol * ratio
        day_sell = 0.0
        day_buy = 0.0
        sell_px: float | None = None
        buy_px: float | None = None

        if i == 0:
            # 首日：只在最低价买入
            day_buy = target
            buy_px = float(low)
            shares += day_buy
            cost += day_buy * buy_px
            net_cost += day_buy * buy_px
            bought += day_buy
        else:
            # 先高价卖，再低价买；卖出不超过当前持仓
            day_sell = min(target, shares)
            if day_sell > 0 and shares > 0:
                sell_px = float(high)
                avg = cost / shares
                cost -= day_sell * avg
                net_cost -= day_sell * sell_px
                shares -= day_sell
                sold += day_sell
                sell_proceeds += day_sell * sell_px
                realized_pnl += day_sell * (sell_px - avg)
                if shares <= 1e-12:
                    shares = 0.0
                    cost = 0.0
                    # 净成本不清零：已回笼盈亏并入后续买入，摊薄净成本

            day_buy = target
            buy_px = float(low)
            shares += day_buy
            cost += day_buy * buy_px
            net_cost += day_buy * buy_px
            bought += day_buy

        if return_history:
            avg_now = (cost / shares) if shares > 0 else None
            net_avg_now = (net_cost / shares) if shares > 0 else None
            history.append(
                {
                    "date": d,
                    "volume_shares": round(vol, 4),
                    "target": round(target, 4),
                    "high": float(high),
                    "low": float(low),
                    "sell": round(day_sell, 4),
                    "sell_price": sell_px,
                    "buy": round(day_buy, 4),
                    "buy_price": buy_px,
                    "shares": round(shares, 4),
                    "avg_price": None if avg_now is None else round(avg_now, 6),
                    "cost": round(cost, 4),
                    "net_cost": round(net_cost, 4),
                    "net_avg_price": None if net_avg_now is None else round(net_avg_now, 6),
                }
            )

    avg_price = (cost / shares) if shares > 0 else None
    net_avg_price = (net_cost / shares) if shares > 0 else None
    unrealized_pnl = 0.0
    if shares > 0 and avg_price is not None and last_close is not None:
        unrealized_pnl = shares * (last_close - avg_price)
    total_pnl = realized_pnl + unrealized_pnl
    used_end = _bar_date(ordered[-1])

    out: dict[str, Any] = {
        "beg": _bar_date(ordered[0]),
        "end": used_end,
        "input_beg": beg_iso,
        "input_end": _iso(end) if end else None,
        "ratio": float(ratio),
        "count": len(ordered),
        "shares": round(shares, 4),
        "avg_price": None if avg_price is None else round(avg_price, 6),
        "cost": round(cost, 4),
        "net_cost": round(net_cost, 4),
        "net_avg_price": None if net_avg_price is None else round(net_avg_price, 6),
        "bought": round(bought, 4),
        "sold": round(sold, 4),
        "sell_proceeds": round(sell_proceeds, 4),
        "close": None if last_close is None else round(last_close, 6),
        "realized_pnl": round(realized_pnl, 4),
        "unrealized_pnl": round(unrealized_pnl, 4),
        "pnl": round(total_pnl, 4),
    }
    if return_history:
        out["history"] = history
    return out
