"""趋势分析规则：仅资金动向列表 + 分时成交列表。

不做日线、东财分档资金、分钟资金、快照。散户「数量」是小单活跃度代理。
"""

from __future__ import annotations

from typing import Any

_SMALL_LOT = 50

_LOT_BUCKETS = (
    ("xs", 0, 20),
    ("s", 21, 50),
    ("m", 51, 200),
    ("l", 201, 500),
    ("xl", 501, 10**9),
)

_AMOUNT_BUCKETS = (
    ("30万以下", 0.0, 300_000.0),
    ("30-100万", 300_000.0, 1_000_000.0),
    ("100-300万", 1_000_000.0, 3_000_000.0),
    ("300万+", 3_000_000.0, 1e18),
)

_SESSION_ORDER = ("auction", "open30", "morning", "afternoon", "late", "close30", "other")


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


def _yi(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / 1e8, 4)


def _pct(num: float, den: float) -> float | None:
    if den <= 0:
        return None
    return round(num / den, 4)


def _hm(value: Any) -> str:
    s = str(value or "")
    if len(s) >= 5 and s[2] == ":":
        return s[:5]
    return s[:5] if s else ""


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


def _quad_key(side: str, aggr: str) -> str | None:
    if side == "buy" and aggr == "active":
        return "active_buy"
    if side == "sell" and aggr == "active":
        return "active_sell"
    if side == "buy" and aggr == "passive":
        return "passive_buy"
    if side == "sell" and aggr == "passive":
        return "passive_sell"
    return None


def analyze_fund(pack: dict[str, Any]) -> dict[str, Any]:
    """资金动向列表（同花顺大单）统计 + 当日标签。"""
    deals = sorted(
        _items(pack.get("big_deal")),
        key=lambda r: (str(r.get("time") or ""), str(r.get("event_id") or "")),
    )

    quad = {
        "active_buy": {"count": 0, "amount": 0.0},
        "active_sell": {"count": 0, "amount": 0.0},
        "passive_buy": {"count": 0, "amount": 0.0},
        "passive_sell": {"count": 0, "amount": 0.0},
    }
    deal_sessions: dict[str, dict[str, float]] = {
        k: {"active_buy": 0.0, "active_sell": 0.0, "count": 0.0} for k in _SESSION_ORDER
    }
    amount_stats = {
        name: {"count": 0, "amount": 0.0, "active_buy": 0.0, "active_sell": 0.0}
        for name, _, _ in _AMOUNT_BUCKETS
    }
    top_events: list[dict[str, Any]] = []

    for row in deals:
        amt = _f(row.get("amount")) or 0.0
        side = str(row.get("side") or "").lower()
        aggr = str(row.get("aggressor") or "").lower()
        key = _quad_key(side, aggr)
        if key:
            quad[key]["count"] += 1
            quad[key]["amount"] += amt
        hm = _hm(row.get("time"))
        sb = _session_bucket(hm)
        if sb == "noon":
            sb = "other"
        sess = deal_sessions.setdefault(sb, {"active_buy": 0.0, "active_sell": 0.0, "count": 0.0})
        sess["count"] += 1
        if key in {"active_buy", "active_sell"}:
            sess[key] += amt
        for name, lo, hi in _AMOUNT_BUCKETS:
            if lo <= amt < hi:
                bucket = amount_stats[name]
                bucket["count"] += 1
                bucket["amount"] += amt
                if key == "active_buy":
                    bucket["active_buy"] += amt
                elif key == "active_sell":
                    bucket["active_sell"] += amt
                break
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
    net_active = active_buy - active_sell

    streak = _active_streak(deals)
    open_net = deal_sessions["open30"]["active_buy"] - deal_sessions["open30"]["active_sell"]
    close_net = deal_sessions["close30"]["active_buy"] - deal_sessions["close30"]["active_sell"]

    label = "观望"
    evidence: list[str] = []
    if len(deals) < 5:
        label = "观望"
        evidence.append(f"大单样本仅 {len(deals)} 笔，不足以下方向")
    elif active_total > 0 and abs(active_buy - active_sell) / active_total < 0.15:
        label = "对倒"
        evidence.append("主动买/卖金额接近，疑似对倒或对敲")
    elif abs(open_net) > 1e5 and abs(close_net) > 1e5 and (open_net > 0) != (close_net > 0):
        label = "分歧"
        evidence.append("开盘30分钟与尾盘30分钟主动净额方向相反")
    elif net_active > 0 and (active_buy_share is None or active_buy_share >= 0.55):
        label = "偏吸"
        evidence.append("当日主动买净额为正")
        if active_buy_share is not None:
            evidence.append(f"主动买占比 {active_buy_share:.0%}")
    elif net_active < 0 and (active_buy_share is None or active_buy_share <= 0.45):
        label = "偏抛"
        evidence.append("当日主动卖净额为正")
        if active_buy_share is not None:
            evidence.append(f"主动买占比仅 {active_buy_share:.0%}")
    elif net_active > 0:
        label = "偏吸"
        evidence.append("当日主动买净额为正，但主动买占比不够一边倒")
    elif net_active < 0:
        label = "偏抛"
        evidence.append("当日主动卖净额为正，但主动卖占比不够一边倒")

    if streak["days"] >= 3:
        evidence.append(
            f"最近连续 {streak['days']} 笔主动单为"
            f"{'买' if streak['direction'] == 'in' else '卖'}"
        )

    return {
        "label": label,
        "evidence": evidence,
        "big_deal_count": len(deals),
        "quad": {k: {"count": v["count"], "amount_yi": _yi(v["amount"])} for k, v in quad.items()},
        "active_buy_yi": _yi(active_buy),
        "active_sell_yi": _yi(active_sell),
        "passive_buy_yi": _yi(quad["passive_buy"]["amount"]),
        "passive_sell_yi": _yi(quad["passive_sell"]["amount"]),
        "active_buy_share": active_buy_share,
        "net_active_yi": _yi(net_active),
        "streak": streak,
        "deal_sessions": {
            k: {
                "active_buy_yi": _yi(v.get("active_buy")),
                "active_sell_yi": _yi(v.get("active_sell")),
                "count": int(v.get("count") or 0),
            }
            for k, v in deal_sessions.items()
            if v.get("count")
        },
        "amount_buckets": [
            {
                "bucket": name,
                "count": v["count"],
                "amount_yi": _yi(v["amount"]),
                "active_buy_yi": _yi(v["active_buy"]),
                "active_sell_yi": _yi(v["active_sell"]),
            }
            for name, v in amount_stats.items()
        ],
        "top_events": top_events,
    }


def _active_streak(deals: list[dict[str, Any]]) -> dict[str, Any]:
    """从最近一笔主动单往回数连续同向笔数。days 字段兼容旧报告（此处为笔数）。"""
    direction = 0
    n = 0
    for row in reversed(deals):
        side = str(row.get("side") or "").lower()
        aggr = str(row.get("aggressor") or "").lower()
        if aggr != "active":
            continue
        sign = 1 if side == "buy" else (-1 if side == "sell" else 0)
        if sign == 0:
            continue
        if direction == 0:
            direction = sign
        if sign == direction:
            n += 1
        else:
            break
    if n == 0:
        return {"direction": "flat", "days": 0}
    return {"direction": "in" if direction > 0 else "out", "days": n}


def analyze_ticks(pack: dict[str, Any], fund: dict[str, Any] | None = None) -> dict[str, Any]:
    """分时成交列表统计 + 散户代理标签。"""
    ticks_pack = pack.get("ticks") if isinstance(pack.get("ticks"), dict) else {}
    ticks = _items(ticks_pack)
    pre_price = _f(ticks_pack.get("pre_price"))
    last_price = _f(ticks_pack.get("last_price"))
    last_time = str(ticks_pack.get("last_time") or "")

    buy_n = sell_n = auction_n = mid_n = 0
    buy_vol = sell_vol = auction_vol = 0.0
    buy_amt = sell_amt = 0.0
    small_buy_n = small_sell_n = 0
    small_buy_vol = small_sell_vol = 0.0
    small_buy_amt = small_sell_amt = 0.0
    price_buckets: set[str] = set()
    lot_stats: dict[str, dict[str, float]] = {
        name: {"buy_n": 0, "sell_n": 0, "buy_vol": 0.0, "sell_vol": 0.0, "amt": 0.0}
        for name, _, _ in _LOT_BUCKETS
    }
    sessions: dict[str, dict[str, float]] = {}
    minute_ticks: dict[str, dict[str, float]] = {}

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
        if sb == "noon":
            sb = "other"
        sess = _ensure_session(sb)
        sess["n"] += 1
        sess["vol"] += vol
        sess["amt"] += amt

        minute = minute_ticks.setdefault(
            hm, {"n": 0, "buy_n": 0, "sell_n": 0, "first": None, "last": None, "amt": 0.0}
        )
        minute["n"] += 1
        minute["amt"] += amt
        if minute["first"] is None and price is not None:
            minute["first"] = price
        if price is not None:
            minute["last"] = price

        is_auction = side_raw in {"auction", "4"}
        is_buy = side_raw in {"buy", "1", "b"}
        is_sell = side_raw in {"sell", "2", "s"}

        if is_auction:
            auction_n += 1
            auction_vol += vol
            continue

        if is_buy:
            buy_n += 1
            buy_vol += vol
            buy_amt += amt
            sess["buy_n"] += 1
            minute["buy_n"] += 1
        elif is_sell:
            sell_n += 1
            sell_vol += vol
            sell_amt += amt
            sess["sell_n"] += 1
            minute["sell_n"] += 1
        else:
            mid_n += 1

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
                small_buy_amt += amt
                sess["small_buy_n"] += 1
            elif is_sell:
                small_sell_n += 1
                small_sell_vol += vol
                small_sell_amt += amt

    small_n = small_buy_n + small_sell_n
    small_vol = small_buy_vol + small_sell_vol
    small_net_amt = small_buy_amt - small_sell_amt
    trade_n = buy_n + sell_n
    buy_share = _pct(buy_n, trade_n)
    buy_vol_share = _pct(buy_vol, buy_vol + sell_vol)
    small_buy_share = _pct(small_buy_n, small_n)
    tick_amount = buy_amt + sell_amt

    activity = "低"
    if small_n >= 800 or (small_n >= 300 and len(price_buckets) >= 40):
        activity = "高"
    elif small_n >= 150:
        activity = "中"

    stance = "观望"
    if small_buy_share is not None and small_buy_share >= 0.58 and small_net_amt >= 0:
        stance = "偏买"
    elif small_buy_share is not None and small_buy_share <= 0.42 and small_net_amt <= 0:
        stance = "偏卖"
    elif small_net_amt > 1e6:
        stance = "偏买"
    elif small_net_amt < -1e6:
        stance = "偏卖"
    elif small_buy_share is not None:
        if small_buy_share >= 0.55:
            stance = "偏买"
        elif small_buy_share <= 0.45:
            stance = "偏卖"

    main_label = str((fund or {}).get("label") or "")
    relation = "不明"
    if main_label == "偏吸" and stance == "偏买":
        relation = "跟风"
    elif main_label == "偏吸" and stance == "偏卖":
        relation = "背离（散户在出）"
    elif main_label == "偏抛" and stance == "偏买":
        relation = "接盘"
    elif main_label == "偏抛" and stance == "偏卖":
        relation = "同步离场"
    elif main_label in {"对倒", "分歧"}:
        relation = "博弈中"
    elif main_label == "观望":
        relation = "资金样本不足"

    cross = _cross_evidence(fund or {}, sessions, minute_ticks, tick_amount)

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
    for key in _SESSION_ORDER:
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
        f"小单净额 {_yi(small_net_amt)} 亿" if small_net_amt else "小单净额接近零",
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
        "tick_amount_yi": _yi(tick_amount),
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
        "small_net_yi": _yi(small_net_amt),
        "price_bucket_count": len(price_buckets),
        "retail_proxy_score": small_n + len(price_buckets),
        "lot_buckets": lot_out,
        "sessions": session_out,
        "peak_session": peak,
        "cross_evidence": cross,
        "evidence": evidence,
        "deal_coverage": _deal_coverage(fund or {}, tick_amount),
    }


def _deal_coverage(fund: dict[str, Any], tick_amount: float) -> float | None:
    buy = (fund.get("active_buy_yi") or 0) + (fund.get("passive_buy_yi") or 0)
    sell = (fund.get("active_sell_yi") or 0) + (fund.get("passive_sell_yi") or 0)
    deal_amt = ((buy or 0) + (sell or 0)) * 1e8
    return _pct(deal_amt, tick_amount)


def _cross_evidence(
    fund: dict[str, Any],
    sessions: dict[str, dict[str, float]],
    minute_ticks: dict[str, dict[str, float]],
    tick_amount: float,
) -> list[str]:
    cross: list[str] = []
    deal_sess = fund.get("deal_sessions") or {}

    def _session_cross(key: str, title: str) -> None:
        open_deal = deal_sess.get(key) or {}
        open_ab = open_deal.get("active_buy_yi") or 0
        open_as = open_deal.get("active_sell_yi") or 0
        tick = sessions.get(key) or {}
        small_buy = _pct(tick.get("small_buy_n", 0), tick.get("small_n", 0) or 0)
        if open_ab and open_as is not None and open_ab > open_as and small_buy is not None and small_buy < 0.45:
            cross.append(f"{title}：大单偏主动买，小单买占比偏低（大单进、小单偏出）")
        if open_as and open_ab is not None and open_as > open_ab and small_buy is not None and small_buy > 0.55:
            cross.append(f"{title}：大单偏主动卖，小单买占比偏高（警惕接盘）")

    _session_cross("open30", "开盘30分钟")
    _session_cross("close30", "尾盘30分钟")

    coverage = _deal_coverage(fund, tick_amount)
    if coverage is not None:
        cross.append(f"大单金额约占分时估算成交额 {coverage:.0%}")
        if coverage < 0.05 and (fund.get("big_deal_count") or 0) > 0:
            cross.append("大单覆盖率偏低，资金标签应降置信")

    for ev in (fund.get("top_events") or [])[:3]:
        hm = _hm(ev.get("time"))
        minute = minute_ticks.get(hm)
        if not minute or not minute["n"]:
            continue
        share = _pct(minute["buy_n"], minute["buy_n"] + minute["sell_n"])
        first, last = minute.get("first"), minute.get("last")
        move = ""
        if isinstance(first, float) and isinstance(last, float) and first:
            move = f"，该分钟价 {((last / first) - 1) * 100:+.2f}%"
        share_s = f"{share:.0%}" if share is not None else "—"
        side = f"{ev.get('aggressor') or ''}{ev.get('side') or ''}".strip()
        cross.append(f"大单 {hm} {side} 同期分时买占比 {share_s}{move}")

    return cross


analyze_main_force = analyze_fund
analyze_retail = analyze_ticks


def build_verdict(
    fund: dict[str, Any],
    ticks: dict[str, Any],
) -> dict[str, Any]:
    main_label = str(fund.get("label") or "观望")
    retail_stance = str(ticks.get("stance") or "观望")
    relation = str(ticks.get("relation_to_main") or "")
    active_buy_share = fund.get("active_buy_share")
    streak = fund.get("streak") or {}
    conf = 0.45

    if main_label in {"偏吸", "偏抛"}:
        conf = 0.55
    if streak.get("days", 0) >= 3:
        conf = min(0.8, conf + 0.08)
    if active_buy_share is not None:
        if main_label == "偏吸" and active_buy_share >= 0.55:
            conf = min(0.85, conf + 0.08)
        if main_label == "偏抛" and active_buy_share <= 0.45:
            conf = min(0.85, conf + 0.08)
    if fund.get("big_deal_count", 0) < 5:
        conf = max(0.3, conf - 0.15)
    if ticks.get("tick_count", 0) < 100:
        conf = max(0.3, conf - 0.1)
    coverage = ticks.get("deal_coverage")
    if isinstance(coverage, float) and coverage < 0.05 and (fund.get("big_deal_count") or 0) > 0:
        conf = max(0.3, conf - 0.08)

    if relation == "接盘":
        headline = "大单偏抛而分时小单偏买，警惕接盘"
        lean = "谨慎偏空"
    elif relation.startswith("背离") and main_label == "偏吸":
        headline = "大单偏吸，但分时小单偏卖，资金与散户代理背离"
        lean = "谨慎偏多"
        conf = max(0.4, conf - 0.05)
    elif main_label == "偏吸" and retail_stance != "偏卖":
        headline = "大单偏吸、小单未明显接盘，短线资金偏积极"
        lean = "偏多"
        conf = min(0.85, conf + 0.05)
    elif main_label == "偏抛" and retail_stance == "偏卖":
        headline = "大单偏抛且小单同步偏卖，短线资金偏谨慎"
        lean = "偏空"
        conf = min(0.85, conf + 0.05)
    elif main_label == "偏抛":
        headline = "大单偏抛，需观察小单是否在接盘"
        lean = "谨慎偏空"
    elif main_label in {"对倒", "分歧"}:
        headline = "大单主动买卖分歧，等待方向明朗"
        lean = "中性"
    elif main_label == "观望":
        headline = f"资金样本不足，分时小单{retail_stance}"
        lean = "中性"
    else:
        headline = f"大单{main_label}、分时小单{retail_stance}"
        lean = "中性"

    return {
        "headline": headline,
        "lean": lean,
        "confidence": round(conf, 2),
        "main_label": main_label,
        "retail_stance": retail_stance,
        "retail_activity": ticks.get("activity"),
        "relation": relation,
        "invalidation": _invalidation(main_label, fund, ticks),
        "trend_bias": lean,
        "pattern": main_label,
        "resonance": relation or "—",
    }


def _invalidation(label: str, fund: dict[str, Any], ticks: dict[str, Any]) -> str:
    share = fund.get("active_buy_share")
    share_s = f"{share:.0%}" if isinstance(share, float) else "—"
    if label == "偏吸":
        return (
            f"若随后30分钟主动买占比回落至45%以下（当前 {share_s}）"
            "，或小单买占比升至55%以上并伴随大单转主动卖（接盘强化）"
        )
    if label == "偏抛":
        return (
            f"若随后30分钟主动买占比升至55%以上（当前 {share_s}）"
            "，同时小单买占比回落"
        )
    if label in {"对倒", "分歧"}:
        return "若开盘与尾盘主动净额重新同向，且主动买/卖占比拉开超过15个百分点"
    stance = ticks.get("stance") or "观望"
    return f"方向确认前以当日主动买占比与开盘/尾盘交叉为主观察锚；当前小单动向 {stance}"
