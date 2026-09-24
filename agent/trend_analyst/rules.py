"""趋势分析规则：仅资金动向 + 分时成交统计与标签。

不做日线/均线/形态。散户「数量」是小单活跃度代理，不是真实持仓人数。
"""

from __future__ import annotations

from typing import Any


def _f(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _items(pack: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(pack, dict):
        return []
    rows = pack.get("items")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _sum_field(rows: list[dict[str, Any]], key: str) -> float:
    total = 0.0
    for row in rows:
        v = _f(row.get(key))
        if v is not None:
            total += v
    return total


def _yi(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / 1e8, 4)


def _pct(num: float, den: float) -> float | None:
    if den <= 0:
        return None
    return round(num / den, 4)


def _round(value: float | None, nd: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, nd)


def _hm(value: Any) -> str:
    """取 HH:MM。"""
    s = str(value or "")
    if len(s) >= 5 and s[2] == ":":
        return s[:5]
    return s[:5] if s else ""


# --- 资金动向 ---

_SMALL_LOT = 50

_LOT_BUCKETS = (
    ("xs", 0, 20),
    ("s", 21, 50),
    ("m", 51, 200),
    ("l", 201, 500),
    ("xl", 501, 10**9),
)


def _window_nets(rows: list[dict[str, Any]], n: int) -> dict[str, float | None]:
    chunk = rows[-n:] if n > 0 else []
    if not chunk:
        return {
            "main": None,
            "super": None,
            "big": None,
            "mid": None,
            "small": None,
            "bars": 0,
        }
    return {
        "main": _sum_field(chunk, "main_net"),
        "super": _sum_field(chunk, "super_net"),
        "big": _sum_field(chunk, "big_net"),
        "mid": _sum_field(chunk, "mid_net"),
        "small": _sum_field(chunk, "small_net"),
        "bars": len(chunk),
    }


def _streak(rows: list[dict[str, Any]], key: str = "main_net") -> dict[str, Any]:
    if not rows:
        return {"direction": "flat", "days": 0}
    signs: list[int] = []
    for row in reversed(rows):
        v = _f(row.get(key)) or 0.0
        if abs(v) < 1e5:
            signs.append(0)
        else:
            signs.append(1 if v > 0 else -1)
    if not signs or signs[0] == 0:
        return {"direction": "flat", "days": 0}
    d = signs[0]
    n = 0
    for s in signs:
        if s == d:
            n += 1
        else:
            break
    return {"direction": "in" if d > 0 else "out", "days": n}


def _flip_count(rows: list[dict[str, Any]], key: str = "main_net") -> int:
    signs: list[int] = []
    for row in rows:
        v = _f(row.get(key)) or 0.0
        if abs(v) < 1e5:
            continue
        signs.append(1 if v > 0 else -1)
    if len(signs) < 2:
        return 0
    return sum(1 for a, b in zip(signs, signs[1:]) if a != b)


def _align_rate(rows: list[dict[str, Any]], a: str, b: str) -> float | None:
    same = total = 0
    for row in rows:
        va = _f(row.get(a)) or 0.0
        vb = _f(row.get(b)) or 0.0
        if abs(va) < 1e5 or abs(vb) < 1e5:
            continue
        total += 1
        if (va > 0) == (vb > 0):
            same += 1
    return _pct(same, total)


def _session_bucket(hm: str) -> str:
    if not hm or len(hm) < 4:
        return "other"
    try:
        h, m = int(hm[:2]), int(hm[3:5])
    except ValueError:
        return "other"
    mins = h * 60 + m
    if mins < 9 * 60 + 30:
        return "auction"
    if mins < 10 * 60:
        return "open30"
    if mins < 11 * 60 + 30:
        return "morning"
    if mins < 13 * 60:
        return "noon"
    if mins < 14 * 60:
        return "afternoon"
    if mins < 14 * 60 + 30:
        return "late"
    if mins <= 15 * 60:
        return "close30"
    return "other"


def analyze_fund(pack: dict[str, Any]) -> dict[str, Any]:
    """资金动向详细统计 + 主力标签。"""
    daily = sorted(_items(pack.get("fund_daily")), key=lambda r: str(r.get("time") or ""))
    minute = sorted(_items(pack.get("fund_minute")), key=lambda r: str(r.get("time") or ""))
    deals = _items(pack.get("big_deal"))
    snap = pack.get("fund_snapshot") if isinstance(pack.get("fund_snapshot"), dict) else {}

    windows = {n: _window_nets(daily, n) for n in (1, 3, 5, 10, 20)}
    latest = daily[-1] if daily else {}
    streak = _streak(daily)
    flips_20 = _flip_count(daily[-20:])
    main_small_align = _align_rate(daily[-20:], "main_net", "small_net")
    super_main_align = _align_rate(daily[-10:], "super_net", "main_net")

    recent10 = []
    for row in daily[-10:]:
        recent10.append(
            {
                "time": str(row.get("time") or "")[:10],
                "main_yi": _yi(_f(row.get("main_net"))),
                "super_yi": _yi(_f(row.get("super_net"))),
                "big_yi": _yi(_f(row.get("big_net"))),
                "mid_yi": _yi(_f(row.get("mid_net"))),
                "small_yi": _yi(_f(row.get("small_net"))),
                "main_net_pct": _f(row.get("main_net_pct")),
            }
        )

    snapshot = {
        "main_yi": _yi(_f(snap.get("main_net"))),
        "super_yi": _yi(_f(snap.get("super_net"))),
        "big_yi": _yi(_f(snap.get("big_net"))),
        "mid_yi": _yi(_f(snap.get("mid_net"))),
        "small_yi": _yi(_f(snap.get("small_net"))),
        "main_net_pct": _f(snap.get("main_net_pct")),
        "super_net_pct": _f(snap.get("super_net_pct")),
        "big_net_pct": _f(snap.get("big_net_pct")),
        "mid_net_pct": _f(snap.get("mid_net_pct")),
        "small_net_pct": _f(snap.get("small_net_pct")),
    }

    # 分钟资金按时段（东财分钟多为累计净流入 → 差分；否则按点值求和）
    session_nets: dict[str, float] = {
        "open30": 0.0,
        "morning": 0.0,
        "afternoon": 0.0,
        "late": 0.0,
        "close30": 0.0,
        "other": 0.0,
    }
    cumulative_like = True
    if minute:
        vals = [_f(r.get("main_net")) or 0.0 for r in minute]
        pos = sum(1 for v in vals if v > 0)
        neg = sum(1 for v in vals if v < 0)
        peak = max((abs(v) for v in vals), default=0.0)
        if pos > 0 and neg > 0 and peak > 0 and abs(vals[-1]) < peak * 0.9:
            cumulative_like = False
        prev = 0.0
        for row, v in zip(minute, vals):
            delta = (v - prev) if cumulative_like else v
            prev = v if cumulative_like else prev
            hm = _hm(row.get("time"))
            bucket = _session_bucket(hm)
            if bucket == "auction":
                bucket = "open30"
            elif bucket == "noon":
                continue
            if bucket not in session_nets:
                bucket = "other"
            session_nets[bucket] += delta

    session_yi = {k: _yi(v) for k, v in session_nets.items()}
    close_share = None
    total_min = sum(session_nets.values())
    if abs(total_min) > 1e5:
        close_share = _pct(session_nets.get("close30", 0.0), abs(total_min))

    # 大单四象限
    quad = {
        "active_buy": {"count": 0, "amount": 0.0},
        "active_sell": {"count": 0, "amount": 0.0},
        "passive_buy": {"count": 0, "amount": 0.0},
        "passive_sell": {"count": 0, "amount": 0.0},
    }
    deal_sessions: dict[str, dict[str, float]] = {}
    top_events: list[dict[str, Any]] = []
    for row in deals:
        amt = _f(row.get("amount")) or 0.0
        side = str(row.get("side") or "").lower()
        aggr = str(row.get("aggressor") or "").lower()
        key = None
        if side == "buy" and aggr == "active":
            key = "active_buy"
        elif side == "sell" and aggr == "active":
            key = "active_sell"
        elif side == "buy" and aggr == "passive":
            key = "passive_buy"
        elif side == "sell" and aggr == "passive":
            key = "passive_sell"
        if key:
            quad[key]["count"] += 1
            quad[key]["amount"] += amt
        hm = _hm(row.get("time"))
        sb = _session_bucket(hm)
        if sb not in deal_sessions:
            deal_sessions[sb] = {"active_buy": 0.0, "active_sell": 0.0}
        if key in {"active_buy", "active_sell"}:
            deal_sessions[sb][key] += amt
        top_events.append(
            {
                "time": str(row.get("time") or ""),
                "amount_yi": _yi(amt),
                "side": side,
                "aggressor": aggr,
                "event_name": row.get("event_name") or "",
                "price": _f(row.get("price")),
                "volume_lots": _f(row.get("volume_lots")),
            }
        )
    top_events.sort(key=lambda x: abs(x.get("amount_yi") or 0), reverse=True)
    top_events = top_events[:8]

    active_buy = quad["active_buy"]["amount"]
    active_sell = quad["active_sell"]["amount"]
    active_total = active_buy + active_sell
    active_buy_share = _pct(active_buy, active_total)

    main_5 = windows[5]["main"] or 0.0
    main_10 = windows[10]["main"] or 0.0
    super_5 = windows[5]["super"] or 0.0

    label = "观望"
    evidence: list[str] = []
    if abs(main_5) < 1e6 and abs(main_10) < 2e6 and not deals:
        label = "观望"
        evidence.append("近5/10日主力净额接近零且无大单样本")
    elif main_5 > 0 and main_10 > 0 and (active_buy_share is None or active_buy_share >= 0.55):
        label = "吸筹"
        evidence.append("近5日与近10日主力净流入同向")
        if active_buy_share is not None:
            evidence.append(f"大单主动买占比 {active_buy_share:.0%}")
    elif main_5 < 0 and main_10 < 0 and (active_buy_share is None or active_buy_share <= 0.45):
        label = "派发"
        evidence.append("近5日与近10日主力净流出同向")
        if active_buy_share is not None:
            evidence.append(f"大单主动买占比仅 {active_buy_share:.0%}")
    elif main_5 * main_10 < 0:
        label = "分歧"
        evidence.append("近5日与近10日主力净额方向相反")
    elif active_buy > 0 and active_sell > 0 and abs(active_buy - active_sell) / max(active_total, 1) < 0.15:
        label = "对倒"
        evidence.append("大单主动买/卖金额接近，疑似对倒或分歧博弈")
    elif main_5 > 0:
        label = "吸筹"
        evidence.append("近5日主力净流入")
    elif main_5 < 0:
        label = "派发"
        evidence.append("近5日主力净流出")

    align = None
    if abs(super_5) > 1e5 and abs(main_5) > 1e5:
        align = (super_5 > 0) == (main_5 > 0)
        evidence.append("超大单与主力同向" if align else "超大单与主力背离")
    if streak["days"] >= 3:
        evidence.append(
            f"主力连续{streak['days']}日{'流入' if streak['direction'] == 'in' else '流出'}"
        )

    def _win_yi(w: dict[str, Any]) -> dict[str, Any]:
        return {
            "bars": w["bars"],
            "main_yi": _yi(w["main"]),
            "super_yi": _yi(w["super"]),
            "big_yi": _yi(w["big"]),
            "mid_yi": _yi(w["mid"]),
            "small_yi": _yi(w["small"]),
        }

    return {
        "label": label,
        "evidence": evidence,
        "daily_bars": len(daily),
        "windows": {str(k): _win_yi(v) for k, v in windows.items()},
        "main_net_1d_yi": _yi(_f(latest.get("main_net"))),
        "main_net_5d_yi": _yi(main_5),
        "main_net_10d_yi": _yi(main_10),
        "super_net_5d_yi": _yi(super_5),
        "big_net_5d_yi": _yi(windows[5]["big"]),
        "small_net_5d_yi": _yi(windows[5]["small"]),
        "streak": streak,
        "flip_count_20d": flips_20,
        "main_small_align_20d": main_small_align,
        "super_main_align_10d": super_main_align,
        "super_align_main": align,
        "recent_10d": recent10,
        "snapshot": snapshot,
        "snapshot_main_yi": snapshot["main_yi"],
        "snapshot_super_yi": snapshot["super_yi"],
        "snapshot_small_yi": snapshot["small_yi"],
        "minute": {
            "bars": len(minute),
            "cumulative_like": cumulative_like if minute else None,
            "session_main_yi": session_yi,
            "close30_share_of_abs": close_share,
        },
        "big_deal_count": len(deals),
        "quad": {
            k: {"count": v["count"], "amount_yi": _yi(v["amount"])} for k, v in quad.items()
        },
        "active_buy_yi": _yi(active_buy),
        "active_sell_yi": _yi(active_sell),
        "passive_buy_yi": _yi(quad["passive_buy"]["amount"]),
        "passive_sell_yi": _yi(quad["passive_sell"]["amount"]),
        "active_buy_share": active_buy_share,
        "deal_sessions": {
            k: {
                "active_buy_yi": _yi(v.get("active_buy")),
                "active_sell_yi": _yi(v.get("active_sell")),
            }
            for k, v in deal_sessions.items()
        },
        "top_events": top_events,
    }


# --- 分时成交 ---

def analyze_ticks(pack: dict[str, Any], fund: dict[str, Any] | None = None) -> dict[str, Any]:
    """分时成交详细统计 + 散户代理标签。"""
    ticks_pack = pack.get("ticks") if isinstance(pack.get("ticks"), dict) else {}
    ticks = _items(ticks_pack)
    pre_price = _f(ticks_pack.get("pre_price"))
    last_price = _f(ticks_pack.get("last_price"))
    last_time = str(ticks_pack.get("last_time") or "")

    daily = sorted(_items(pack.get("fund_daily")), key=lambda r: str(r.get("time") or ""))
    small_5 = _sum_field(daily[-5:], "small_net") if daily else None
    small_1 = _f(daily[-1].get("small_net")) if daily else None
    snap = pack.get("fund_snapshot") if isinstance(pack.get("fund_snapshot"), dict) else {}
    snap_small = _f(snap.get("small_net"))

    buy_n = sell_n = auction_n = mid_n = 0
    buy_vol = sell_vol = auction_vol = mid_vol = 0.0
    buy_amt = sell_amt = 0.0
    small_buy_n = small_sell_n = 0
    small_buy_vol = small_sell_vol = 0.0
    price_buckets: set[str] = set()
    lot_stats: dict[str, dict[str, float]] = {
        name: {"buy_n": 0, "sell_n": 0, "buy_vol": 0.0, "sell_vol": 0.0, "amt": 0.0}
        for name, _, _ in _LOT_BUCKETS
    }
    sessions: dict[str, dict[str, float]] = {}

    def _ensure_session(sb: str) -> dict[str, float]:
        if sb not in sessions:
            sessions[sb] = {
                "n": 0,
                "buy_n": 0,
                "sell_n": 0,
                "vol": 0.0,
                "amt": 0.0,
                "small_n": 0,
                "small_buy_n": 0,
            }
        return sessions[sb]

    for row in ticks:
        side_raw = str(row.get("side_label") or row.get("side") or "").lower()
        vol = _f(row.get("volume")) or 0.0
        price = _f(row.get("price"))
        amt = _f(row.get("amount"))
        if amt is None and price is not None:
            amt = price * vol * 100.0
        amt = amt or 0.0
        if price is not None:
            price_buckets.add(f"{price:.2f}")

        hm = _hm(row.get("time"))
        sb = _session_bucket(hm)
        sess = _ensure_session(sb)
        sess["n"] += 1
        sess["vol"] += vol
        sess["amt"] += amt

        is_auction = side_raw in {"auction", "4"}
        is_buy = side_raw in {"buy", "1", "b"}
        is_sell = side_raw in {"sell", "2", "s"}
        is_mid = side_raw in {"mid", "0", "m"} or (not is_buy and not is_sell and not is_auction)

        if is_auction:
            auction_n += 1
            auction_vol += vol
            continue

        if is_buy:
            buy_n += 1
            buy_vol += vol
            buy_amt += amt
            sess["buy_n"] += 1
        elif is_sell:
            sell_n += 1
            sell_vol += vol
            sell_amt += amt
            sess["sell_n"] += 1
        else:
            mid_n += 1
            mid_vol += vol

        bucket_name = "xl"
        for name, lo, hi in _LOT_BUCKETS:
            if lo <= vol <= hi:
                bucket_name = name
                break
        ls = lot_stats[bucket_name]
        ls["amt"] += amt
        if is_buy:
            ls["buy_n"] += 1
            ls["buy_vol"] += vol
        elif is_sell:
            ls["sell_n"] += 1
            ls["sell_vol"] += vol

        if vol <= _SMALL_LOT:
            sess["small_n"] += 1
            if is_buy:
                small_buy_n += 1
                small_buy_vol += vol
                sess["small_buy_n"] += 1
            elif is_sell:
                small_sell_n += 1
                small_sell_vol += vol

    small_n = small_buy_n + small_sell_n
    small_vol = small_buy_vol + small_sell_vol
    trade_n = buy_n + sell_n
    buy_share = _pct(buy_n, trade_n)
    buy_vol_share = _pct(buy_vol, buy_vol + sell_vol)
    small_buy_share = _pct(small_buy_n, small_n)

    activity = "低"
    if small_n >= 800 or (small_n >= 300 and len(price_buckets) >= 40):
        activity = "高"
    elif small_n >= 150:
        activity = "中"

    stance = "观望"
    if small_buy_share is not None and small_buy_share >= 0.58 and (small_5 or 0) >= 0:
        stance = "偏买"
    elif small_buy_share is not None and small_buy_share <= 0.42 and (small_5 or 0) <= 0:
        stance = "偏卖"
    elif small_5 is not None and small_5 > 1e6:
        stance = "偏买"
    elif small_5 is not None and small_5 < -1e6:
        stance = "偏卖"
    elif small_buy_share is not None:
        if small_buy_share >= 0.55:
            stance = "偏买"
        elif small_buy_share <= 0.45:
            stance = "偏卖"

    main_label = str((fund or {}).get("label") or "")
    relation = "不明"
    if main_label == "吸筹" and stance == "偏买":
        relation = "跟风"
    elif main_label == "吸筹" and stance == "偏卖":
        relation = "背离（散户在出）"
    elif main_label == "派发" and stance == "偏买":
        relation = "接盘"
    elif main_label == "派发" and stance == "偏卖":
        relation = "同步离场"
    elif main_label in {"对倒", "分歧"}:
        relation = "博弈中"

    # 交叉：开盘大单主动买 vs 小单
    cross: list[str] = []
    deal_sess = (fund or {}).get("deal_sessions") or {}
    open_deal = deal_sess.get("open30") or {}
    open_ab = open_deal.get("active_buy_yi") or 0
    open_as = open_deal.get("active_sell_yi") or 0
    open_tick = sessions.get("open30") or {}
    open_small_buy = _pct(open_tick.get("small_buy_n", 0), open_tick.get("small_n", 0) or 0)
    if open_ab and open_as is not None and open_ab > open_as and open_small_buy is not None and open_small_buy < 0.45:
        cross.append("开盘30分钟：大单偏主动买，小单买占比偏低（大单进、小单偏出）")
    if open_as and open_ab is not None and open_as > open_ab and open_small_buy is not None and open_small_buy > 0.55:
        cross.append("开盘30分钟：大单偏主动卖，小单买占比偏高（警惕接盘）")

    pct_vs_pre = None
    if pre_price and last_price and pre_price > 0:
        pct_vs_pre = round((last_price / pre_price - 1) * 100, 2)

    lot_out = []
    for name, lo, hi in _LOT_BUCKETS:
        ls = lot_stats[name]
        bn, sn = int(ls["buy_n"]), int(ls["sell_n"])
        lot_out.append(
            {
                "bucket": f"{lo}-{hi if hi < 10**8 else '∞'}手",
                "trades": bn + sn,
                "buy_share": _pct(bn, bn + sn),
                "net_vol_lots": round(ls["buy_vol"] - ls["sell_vol"], 1),
                "amount_yi": _yi(ls["amt"]),
            }
        )

    session_out = []
    for key in ("auction", "open30", "morning", "afternoon", "late", "close30", "other"):
        s = sessions.get(key)
        if not s or not s["n"]:
            continue
        session_out.append(
            {
                "session": key,
                "trades": int(s["n"]),
                "buy_share": _pct(s["buy_n"], s["buy_n"] + s["sell_n"]),
                "vol_lots": round(s["vol"], 1),
                "amount_yi": _yi(s["amt"]),
                "small_trades": int(s["small_n"]),
                "small_buy_share": _pct(s["small_buy_n"], s["small_n"]),
            }
        )

    peak = max(session_out, key=lambda x: x["trades"], default=None)

    evidence = [
        f"分时成交 {len(ticks)} 笔，小单(≤{_SMALL_LOT}手) {small_n} 笔",
        f"小单买占比 {small_buy_share:.0%}" if small_buy_share is not None else "小单样本不足",
        f"近5日小单净额 {_yi(small_5)} 亿" if small_5 is not None else "无小单资金序列",
    ]
    evidence.extend(cross)

    return {
        "note": "散户数量为小单活跃度代理，非真实持仓人数",
        "activity": activity,
        "stance": stance,
        "relation_to_main": relation,
        "tick_count": len(ticks),
        "trade_count": trade_n,
        "auction_count": auction_n,
        "mid_count": mid_n,
        "buy_count": buy_n,
        "sell_count": sell_n,
        "buy_share": buy_share,
        "buy_vol_share": buy_vol_share,
        "buy_vol_lots": round(buy_vol, 1),
        "sell_vol_lots": round(sell_vol, 1),
        "auction_vol_lots": round(auction_vol, 1),
        "buy_amount_yi": _yi(buy_amt),
        "sell_amount_yi": _yi(sell_amt),
        "pre_price": pre_price,
        "last_price": last_price,
        "last_time": last_time,
        "pct_vs_pre": pct_vs_pre,
        "small_lot_threshold": _SMALL_LOT,
        "small_trade_count": small_n,
        "small_buy_count": small_buy_n,
        "small_sell_count": small_sell_n,
        "small_buy_share": small_buy_share,
        "small_volume_lots": round(small_vol, 1),
        "price_bucket_count": len(price_buckets),
        "retail_proxy_score": small_n + len(price_buckets),
        "small_net_1d_yi": _yi(snap_small if snap_small is not None else small_1),
        "small_net_5d_yi": _yi(small_5),
        "lot_buckets": lot_out,
        "sessions": session_out,
        "peak_session": peak,
        "cross_evidence": cross,
        "evidence": evidence,
    }


# 兼容旧节点命名
analyze_main_force = analyze_fund
analyze_retail = analyze_ticks


def build_verdict(
    fund: dict[str, Any],
    ticks: dict[str, Any],
) -> dict[str, Any]:
    """仅基于资金 + 分时的综合结论。"""
    main_label = str(fund.get("label") or "观望")
    retail_stance = str(ticks.get("stance") or "观望")
    relation = str(ticks.get("relation_to_main") or "")
    active_buy_share = fund.get("active_buy_share")
    streak = fund.get("streak") or {}
    main_5 = fund.get("main_net_5d_yi")
    conf = 0.45

    if main_label in {"吸筹", "派发"}:
        conf = 0.55
    if streak.get("days", 0) >= 3:
        conf = min(0.8, conf + 0.1)
    if active_buy_share is not None:
        if main_label == "吸筹" and active_buy_share >= 0.55:
            conf = min(0.85, conf + 0.08)
        if main_label == "派发" and active_buy_share <= 0.45:
            conf = min(0.85, conf + 0.08)
    if fund.get("big_deal_count", 0) < 5 and (fund.get("daily_bars") or 0) < 5:
        conf = max(0.3, conf - 0.15)
    if ticks.get("tick_count", 0) < 100:
        conf = max(0.3, conf - 0.1)

    if relation == "接盘":
        headline = "主力流出而分时小单偏买，警惕接盘"
        lean = "谨慎偏空"
    elif relation.startswith("背离") and main_label == "吸筹":
        headline = "主力偏吸筹，但分时小单偏卖，资金与散户代理背离"
        lean = "谨慎偏多"
        conf = max(0.4, conf - 0.05)
    elif main_label == "吸筹" and retail_stance != "偏卖":
        headline = "主力偏吸筹、小单未明显接盘，短线资金偏积极"
        lean = "偏多"
        conf = min(0.85, conf + 0.05)
    elif main_label == "派发" and retail_stance == "偏卖":
        headline = "主力偏派发且小单同步偏卖，短线资金偏谨慎"
        lean = "偏空"
        conf = min(0.85, conf + 0.05)
    elif main_label == "派发":
        headline = "主力偏派发，需观察小单是否在接盘"
        lean = "谨慎偏空"
    elif main_label in {"对倒", "分歧"}:
        headline = "大单或主力资金方向分歧，等待资金信号明朗"
        lean = "中性"
    else:
        headline = f"主力{main_label}、分时小单{retail_stance}"
        lean = "中性" if main_label == "观望" else ("偏多" if main_label == "吸筹" else "偏空")

    return {
        "headline": headline,
        "lean": lean,
        "confidence": round(conf, 2),
        "main_label": main_label,
        "retail_stance": retail_stance,
        "retail_activity": ticks.get("activity"),
        "relation": relation,
        "invalidation": _invalidation(main_label, fund, ticks),
        # 兼容旧字段名（前端/旧报告）
        "trend_bias": lean,
        "pattern": main_label,
        "resonance": relation or "—",
    }


def _invalidation(label: str, fund: dict[str, Any], ticks: dict[str, Any]) -> str:
    share = fund.get("active_buy_share")
    share_s = f"{share:.0%}" if isinstance(share, float) else "—"
    if label == "吸筹":
        return (
            f"若近2日主力转净流出，且大单主动买占比回落至45%以下（当前 {share_s}）"
            "，或小单由偏卖翻为持续偏买并伴随主力转出（接盘强化）"
        )
    if label == "派发":
        return (
            f"若近2日主力转净流入，且大单主动买占比升至55%以上（当前 {share_s}）"
            "，同时小单买占比回落"
        )
    if label in {"对倒", "分歧"}:
        return "若近5日主力与超大单方向重新同向，且主动买/卖占比拉开超过15个百分点"
    stance = ticks.get("stance") or "观望"
    return f"方向确认前以主力近5日净额与大单主动买占比为主观察锚；当前小单动向 {stance}"
