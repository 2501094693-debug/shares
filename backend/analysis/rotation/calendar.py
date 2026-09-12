"""过去每天哪些三级上榜，哪些距上次上榜最久。

三级没有官方指数。涨跌 = 成分股市值加权。
优先读每日收盘快照；缺日再用成分股日 K 回填。
上榜 = 涨幅强度、上涨占比、进攻扩散三项软评分大于 60。
涨幅强度 = 当天加权涨幅 / 近 20 个交易日（不含当天）样本标准差。
"""

from __future__ import annotations

import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any

from analysis.decline.bars import parse_bars
from analysis.rotation.config import (
    CAP_MID_YI,
    CAP_WEIGHT_YI,
    DEFAULT_LOOKBACK_DAYS,
    KLINE_LIMIT,
    KLINE_WORKERS,
    MAX_LOOKBACK_DAYS,
    MIN_LOOKBACK_DAYS,
    MIN_STOCKS,
    SCORE_NAMED,
    SIGMA_DAYS,
    STRONG_MID_PCT,
    STRONG_THEME_PCT,
    STRONG_WEIGHT_PCT,
    WATCH_CHANGE_PCT,
)
from analysis.rotation.daycache import day_frozen, load_l3_day, save_l3_day
from analysis.rotation.score import cap_tier_of, score_row, trailing_sigma
from company.line.fetcher import fetch_kline, load_kline_disk
from company.line.session import is_cn_market_live
from core.codes import normalize_code
from industry.service import service as industry_service
from market.steep.calendar import recent_trade_dates
from market.sw.fund_flow import aggregate_stock_flows_all
from market.steep.service import service as steep_service
from market.sw.history import load_local_snapshot, snapshot_day
from market.sw.parse import parse_pct, parse_yi
from market.sw.service import service as market_service
from market.sw.taxonomy import flatten_tree

_SOURCE_SNAPSHOT = "snapshot"
_SOURCE_LIVE = "live"
_SOURCE_KLINE = "kline"
_SOURCE_MISSING = "missing"
_QUOTE_KEYS = (
    "change_1d",
    "up_1d",
    "down_1d",
    "limit_up_1d",
    "limit_down_1d",
    "strong_1d",
)


def clamp_days(days: int) -> int:
    try:
        value = int(days)
    except (TypeError, ValueError) as exc:
        raise ValueError("days 须为整数") from exc
    if value < MIN_LOOKBACK_DAYS or value > MAX_LOOKBACK_DAYS:
        raise ValueError(f"days 须在 {MIN_LOOKBACK_DAYS}–{MAX_LOOKBACK_DAYS} 之间")
    return value


def _iso(raw: str) -> str:
    text = str(raw or "").strip().replace("-", "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return str(raw or "").strip()[:10]


def _as_date(iso: str) -> date:
    return date.fromisoformat(iso)


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _weighted(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    if total_w > 0:
        return sum(v * w for v, w in pairs) / total_w
    return sum(v for v, _ in pairs) / len(pairs)


def _trade_dates(days: int) -> list[str]:
    raws = recent_trade_dates(days)
    out: list[str] = []
    seen: set[str] = set()
    for raw in raws:
        iso = _iso(raw)
        if len(iso) != 10 or iso in seen:
            continue
        seen.add(iso)
        out.append(iso)
    return out


def _bare6(value: Any) -> str:
    text = "".join(ch for ch in str(value or "") if ch.isdigit())
    return text[-6:] if len(text) >= 6 else text


def _looks_limit_up(code: str, name: str, pct: float) -> bool:
    title = str(name or "")
    if "ST" in title.upper():
        return pct >= 4.8
    bare = _bare6(code)
    if bare.startswith(("688", "300")):
        return pct >= 19.5
    if bare.startswith(("8", "4")) and not bare.startswith("688"):
        return pct >= 29.5
    return pct >= 9.5


def _looks_limit_down(code: str, name: str, pct: float) -> bool:
    return _looks_limit_up(code, name, -pct) if pct < 0 else False


def _cap_yi(cap: float) -> float:
    if cap >= 1e6:
        return cap / 1e8
    return cap


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    mid = len(xs) // 2
    if len(xs) % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def _is_wide_board(code: str) -> bool:
    bare = _bare6(code)
    return bare.startswith(("688", "300", "8", "4"))


def _is_strong(code: str, name: str, pct: float, cap: float) -> bool:
    if _looks_limit_up(code, name, pct):
        return True
    yi = _cap_yi(cap)
    if _is_wide_board(code) or yi < CAP_MID_YI:
        return pct >= STRONG_THEME_PCT
    if yi >= CAP_WEIGHT_YI:
        return pct >= STRONG_WEIGHT_PCT
    return pct >= STRONG_MID_PCT


def _leader_of(children: list[dict[str, Any]]) -> str:
    best = ""
    best_cap = -1.0
    for child in children:
        cap = parse_yi(child.get("market_cap")) or 0.0
        if cap > best_cap:
            best_cap = cap
            best = str(child.get("name") or "")
    return best


def _l3_from_node(
    l1: dict[str, Any], l2: dict[str, Any], l3: dict[str, Any]
) -> dict[str, Any] | None:
    code = str(l3.get("code") or "").strip()
    if not code:
        return None
    children = [c for c in (l3.get("children") or []) if isinstance(c, dict)]
    stocks = [c for c in children if int(c.get("level") or 0) != 3]
    sample = l3.get("sample_count")
    up = l3.get("up_count")
    down = l3.get("down_count")
    zt = l3.get("limit_up_count")
    dt = l3.get("limit_down_count")
    chg = parse_pct(l3.get("change_pct"))
    pairs: list[tuple[float, float]] = []
    caps: list[float] = []
    up_from_stocks = 0
    down_from_stocks = 0
    zt_from_stocks = 0
    dt_from_stocks = 0
    strong_n = 0
    for stock in stocks:
        cap = parse_yi(stock.get("market_cap")) or 0.0
        if cap > 0:
            caps.append(cap)
        pct = parse_pct(stock.get("change_pct") or stock.get("change_1d"))
        if pct is None:
            continue
        name = str(stock.get("name") or "")
        code_s = str(stock.get("code") or "")
        pairs.append((pct, cap))
        if pct > 0:
            up_from_stocks += 1
        elif pct < 0:
            down_from_stocks += 1
        if _looks_limit_up(code_s, name, pct):
            zt_from_stocks += 1
        if _looks_limit_down(code_s, name, pct):
            dt_from_stocks += 1
        if _is_strong(code_s, name, pct, cap):
            strong_n += 1
    if chg is None:
        chg = _weighted(pairs)
    if sample is None:
        sample = len(pairs)
    if up is None:
        up = up_from_stocks
    if down is None:
        down = down_from_stocks
    if zt is None:
        zt = zt_from_stocks
    if dt is None:
        dt = dt_from_stocks
    if not pairs and zt:
        strong_n = int(zt or 0)
    try:
        sample_n = int(sample or 0)
    except (TypeError, ValueError):
        sample_n = 0
    try:
        up_n = int(up or 0)
    except (TypeError, ValueError):
        up_n = 0
    try:
        down_n = int(down or 0)
    except (TypeError, ValueError):
        down_n = 0
    try:
        zt_n = int(zt or 0)
    except (TypeError, ValueError):
        zt_n = 0
    try:
        dt_n = int(dt or 0)
    except (TypeError, ValueError):
        dt_n = 0
    if chg is None:
        return None
    meta = industry_service.get_l3_meta(code) or {}
    return {
        "code": code,
        "name": meta.get("name") or str(l3.get("name") or code),
        "l1_code": str(meta.get("l1_code") or l1.get("code") or ""),
        "l1_name": meta.get("l1_name") or str(l1.get("name") or ""),
        "l2_code": str(meta.get("l2_code") or l2.get("code") or ""),
        "l2_name": meta.get("l2_name") or str(l2.get("name") or ""),
        "change_1d": _round(chg),
        "up_1d": up_n,
        "down_1d": down_n,
        "limit_up_1d": zt_n,
        "limit_down_1d": dt_n,
        "strong_1d": strong_n,
        "cap_median": _round(_cap_yi(_median(caps)), 1),
        "cap_tier": cap_tier_of(_cap_yi(_median(caps))),
        "sample_count": sample_n,
        "leader": _leader_of(stocks) or str(l3.get("leader") or ""),
    }


def _l3_from_tree(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for l1 in tree or []:
        if not isinstance(l1, dict):
            continue
        for l2 in l1.get("children") or []:
            if not isinstance(l2, dict):
                continue
            for l3 in l2.get("children") or []:
                if not isinstance(l3, dict):
                    continue
                if int(l3.get("level") or 3) not in {0, 3}:
                    continue
                row = _l3_from_node(l1, l2, l3)
                if row is not None:
                    rows.append(row)
    return rows


def _payload_tree(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    tree = payload.get("tree")
    return tree if isinstance(tree, list) else []


def _latest_l3_quotes() -> dict[str, dict[str, Any]]:
    """待涨展示用最新行业树报价，不依赖轮动缓存里有没有 1 日字段。"""
    rows: list[dict[str, Any]] = []
    try:
        rows = _l3_from_tree(_payload_tree(load_local_snapshot()))
    except Exception:
        rows = []
    if not rows:
        try:
            live = market_service.tree(force=False, lite=True)
            rows = _l3_from_tree(_payload_tree(live))
        except Exception:
            rows = []
    return {
        str(row.get("code") or ""): row
        for row in rows
        if isinstance(row, dict) and row.get("code")
    }


def _paint_quotes(
    rows: list[dict[str, Any]] | None, quotes: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    if not rows:
        return []
    if not quotes:
        return [dict(row) for row in rows if isinstance(row, dict)]
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        quote = quotes.get(str(item.get("code") or ""))
        if quote:
            for key in _QUOTE_KEYS:
                if quote.get(key) is not None:
                    item[key] = quote.get(key)
        out.append(item)
    return out


def _universe(stocks: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    counts: dict[str, int] = defaultdict(int)
    out: dict[str, dict[str, str]] = {}
    for stock in stocks:
        code = str(stock.get("l3_code") or "").strip()
        if not code:
            continue
        counts[code] += 1
        if code in out:
            continue
        meta = industry_service.get_l3_meta(code) or {}
        out[code] = {
            "code": code,
            "name": meta.get("name") or str(stock.get("l3_name") or code),
            "l1_code": str(meta.get("l1_code") or ""),
            "l1_name": meta.get("l1_name") or str(stock.get("l1_name") or ""),
            "l2_code": str(meta.get("l2_code") or ""),
            "l2_name": meta.get("l2_name") or str(stock.get("l2_name") or ""),
        }
    return {code: row for code, row in out.items() if counts[code] >= MIN_STOCKS}


def _prior_changes(
    history: dict[str, dict[str, float]],
    code: str,
    iso: str,
    chronological: list[str],
) -> list[float]:
    series = history.get(code) or {}
    prior: list[float] = []
    for day in chronological:
        if day >= iso:
            break
        val = series.get(day)
        if val is None:
            continue
        prior.append(float(val))
    return prior[-SIGMA_DAYS:]


def _pick_named(
    rows: list[dict[str, Any]],
    *,
    iso: str,
    chronological: list[str],
    history: dict[str, dict[str, float]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible = [r for r in rows if int(r.get("sample_count") or 0) >= MIN_STOCKS]
    scored: list[dict[str, Any]] = []
    for row in eligible:
        if row.get("change_1d") is None:
            continue
        sigma = trailing_sigma(
            _prior_changes(history, str(row.get("code") or ""), iso, chronological)
        )
        scored.append(score_row(row, sigma=sigma))
    scored.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    for index, item in enumerate(scored, 1):
        item["score_rank"] = index
    named = [item for item in scored if item.get("named")]
    return named, scored


def _day_from_snapshot(iso: str, *, force: bool = False) -> tuple[list[dict[str, Any]], str] | None:
    payload = load_local_snapshot(_as_date(iso))
    rows = _l3_from_tree(_payload_tree(payload))
    if rows:
        return rows, _SOURCE_SNAPSHOT
    today = snapshot_day().isoformat()
    if iso != today:
        return None
    if not force and not is_cn_market_live():
        return None
    try:
        live = market_service.tree(force=force, lite=False)
    except Exception:  # noqa: BLE001
        return None
    rows = _l3_from_tree(_payload_tree(live))
    if rows:
        return rows, _SOURCE_LIVE
    return None


def _bare_stock_code(stock: dict[str, Any]) -> str:
    try:
        return normalize_code(stock.get("code") or "")
    except Exception:  # noqa: BLE001
        return ""


def _pcts_from_bars(bars: list[dict[str, Any]], needed: set[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for idx, bar in enumerate(bars):
        day = str(bar.get("date") or "")
        if day not in needed:
            continue
        pct = bar.get("pct_chg")
        if pct is None and idx > 0:
            prev = bars[idx - 1].get("close")
            close = bar.get("close")
            if prev and close:
                pct = (float(close) / float(prev) - 1.0) * 100.0
        if pct is None:
            continue
        out[day] = float(pct)
    return out


def _disk_covers(bars: list[dict[str, Any]], needed: set[str]) -> bool:
    if not bars or not needed:
        return False
    last = str(bars[-1].get("date") or "")
    return bool(last) and last >= max(needed)


def _stock_day_pct(code: str, needed: set[str], force: bool) -> dict[str, float]:
    if not force:
        stored = load_kline_disk(code)
        bars = parse_bars((stored or {}).get("items") or [])
        if _disk_covers(bars, needed):
            return _pcts_from_bars(bars, needed)
    pack = fetch_kline(
        code,
        period="day",
        adjust="qfq",
        limit=max(KLINE_LIMIT, len(needed) + 8),
        force=force,
    )
    bars = parse_bars((pack or {}).get("items") or [])
    return _pcts_from_bars(bars, needed)


def _backfill_kline(
    dates: list[str],
    stocks: list[dict[str, Any]],
    *,
    force: bool,
    workers: int,
    errors: list[str],
) -> dict[str, list[dict[str, Any]]]:
    needed = set(dates)
    buckets: dict[str, dict[str, dict[str, Any]]] = {day: {} for day in dates}

    def one(stock: dict[str, Any]) -> list[tuple[str, str, float, float, str, str, str, str, str]]:
        l3 = str(stock.get("l3_code") or "").strip()
        code = _bare_stock_code(stock)
        if not l3 or not code:
            return []
        try:
            pcts = _stock_day_pct(code, needed, force)
        except Exception:  # noqa: BLE001
            return []
        if not pcts:
            return []
        cap = parse_yi(stock.get("market_cap")) or 0.0
        name = str(stock.get("name") or "")
        l3_name = str(stock.get("l3_name") or l3)
        l1_name = str(stock.get("l1_name") or "")
        l2_name = str(stock.get("l2_name") or "")
        return [
            (day, l3, pct, cap, name, l3_name, l1_name, l2_name, code)
            for day, pct in pcts.items()
        ]

    jobs = [s for s in stocks if str(s.get("l3_code") or "").strip() and _bare_stock_code(s)]
    if not jobs:
        errors.append("没有成分股，无法用日 K 回填三级涨幅")
        return {day: [] for day in dates}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(one, stock) for stock in jobs]
        for fut in as_completed(futures):
            try:
                rows = fut.result()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"日K回填: {exc}")
                continue
            for day, l3, pct, cap, name, l3_name, l1_name, l2_name, code in rows:
                dest = buckets[day].get(l3)
                if dest is None:
                    dest = {
                        "code": l3,
                        "name": l3_name,
                        "l1_name": l1_name,
                        "l2_name": l2_name,
                        "pairs": [],
                        "caps": [],
                        "up": 0,
                        "down": 0,
                        "zt": 0,
                        "dt": 0,
                        "strong": 0,
                        "leader": "",
                        "leader_cap": -1.0,
                    }
                    buckets[day][l3] = dest
                dest["pairs"].append((pct, cap))
                if cap > 0:
                    dest["caps"].append(cap)
                if pct > 0:
                    dest["up"] += 1
                elif pct < 0:
                    dest["down"] += 1
                if _looks_limit_up(code, name, pct):
                    dest["zt"] += 1
                if _looks_limit_down(code, name, pct):
                    dest["dt"] += 1
                if _is_strong(code, name, pct, cap):
                    dest["strong"] += 1
                if cap > dest["leader_cap"]:
                    dest["leader_cap"] = cap
                    dest["leader"] = name

    out: dict[str, list[dict[str, Any]]] = {}
    for day in dates:
        rows: list[dict[str, Any]] = []
        for dest in buckets[day].values():
            pairs = dest["pairs"]
            if len(pairs) < MIN_STOCKS:
                continue
            chg = _weighted(pairs)
            if chg is None:
                continue
            meta = industry_service.get_l3_meta(dest["code"]) or {}
            rows.append(
                {
                    "code": dest["code"],
                    "name": meta.get("name") or dest["name"],
                    "l1_code": str(meta.get("l1_code") or ""),
                    "l1_name": meta.get("l1_name") or dest["l1_name"],
                    "l2_code": str(meta.get("l2_code") or ""),
                    "l2_name": meta.get("l2_name") or dest["l2_name"],
                    "change_1d": _round(chg),
                    "up_1d": dest["up"],
                    "down_1d": dest["down"],
                    "limit_up_1d": dest["zt"],
                    "limit_down_1d": dest["dt"],
                    "strong_1d": dest["strong"],
                    "cap_median": _round(_cap_yi(_median(dest["caps"])), 1),
                    "cap_tier": cap_tier_of(_cap_yi(_median(dest["caps"]))),
                    "sample_count": len(pairs),
                    "leader": dest["leader"],
                }
            )
        out[day] = rows
    return out


def _current_metrics(stocks: list[dict[str, Any]], errors: list[str]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for stock in stocks:
        l3 = str(stock.get("l3_code") or "").strip()
        if not l3:
            continue
        dest = buckets.get(l3)
        if dest is None:
            dest = {
                "d5": [],
                "ytd": [],
                "up_5d": 0,
                "sample": 0,
                "leader": "",
                "leader_cap": -1.0,
            }
            buckets[l3] = dest
        cap = parse_yi(stock.get("market_cap")) or 0.0
        d5 = parse_pct(stock.get("change_5d"))
        ytd = parse_pct(stock.get("change_ytd"))
        dest["sample"] += 1
        if d5 is not None:
            dest["d5"].append((d5, cap))
            if d5 > 0:
                dest["up_5d"] += 1
        if ytd is not None:
            dest["ytd"].append((ytd, cap))
        if cap > dest["leader_cap"]:
            dest["leader_cap"] = cap
            dest["leader"] = str(stock.get("name") or "")

    rows: dict[str, dict[str, Any]] = {}
    for code, dest in buckets.items():
        if dest["sample"] < MIN_STOCKS:
            continue
        rows[code] = {
            "change_5d": _round(_weighted(dest["d5"])),
            "change_ytd": _round(_weighted(dest["ytd"])),
            "up_5d": dest["up_5d"],
            "sample_count": dest["sample"],
            "leader": dest["leader"],
            "main_net": None,
            "main_net_5d": None,
            "main_net_10d": None,
        }

    try:
        nodes = flatten_tree(industry_service.get_tree())
        flows = market_service._raw_stock_flows(force=False)
        flow_map = aggregate_stock_flows_all(nodes, stocks, flows)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"资金流: {exc}")
        return rows
    for code, row in rows.items():
        extra = flow_map.get(code) or {}
        row["main_net"] = _round(extra.get("main_net"), 0)
        row["main_net_5d"] = _round(extra.get("main_net_5d"), 0)
        row["main_net_10d"] = _round(extra.get("main_net_10d"), 0)
    return rows


def _merge_metrics(row: dict[str, Any], metrics: dict[str, Any] | None) -> dict[str, Any]:
    extra = metrics or {}
    out = dict(row)
    for key in (
        "change_5d",
        "change_ytd",
        "up_5d",
        "main_net",
        "main_net_5d",
        "main_net_10d",
    ):
        if extra.get(key) is not None:
            out[key] = extra.get(key)
    if extra.get("leader") and not out.get("leader"):
        out["leader"] = extra["leader"]
    if extra.get("sample_count") and not out.get("sample_count"):
        out["sample_count"] = extra["sample_count"]
    return out


def _untouched_tag(row: dict[str, Any]) -> tuple[str, str]:
    flow5 = row.get("main_net_5d")
    flow10 = row.get("main_net_10d")
    d5 = row.get("change_5d")
    money = flow5 is not None and flow5 > 0 and flow10 is not None and flow10 > 0
    if money and (d5 is None or float(d5) < WATCH_CHANGE_PCT):
        return "资金先行", "窗口内没被点名，但5日和10日资金都在进"
    if d5 is not None and float(d5) >= WATCH_CHANGE_PCT:
        return "近5日跟上", "窗口内没被点名，近5日已经转强"
    return "", "窗口内从未达到轮动分数线"


def _stock_l3_map(stocks: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for stock in stocks:
        code = _bare6(stock.get("code") or "")
        l3 = str(stock.get("l3_code") or "").strip()
        if code and l3 and code not in out:
            out[code] = l3
    return out


def _limit_maps(
    dates: list[str], stocks: list[dict[str, Any]]
) -> dict[str, dict[str, dict[str, int]]]:
    mapping = _stock_l3_map(stocks)
    out: dict[str, dict[str, dict[str, int]]] = {}
    for iso in dates:
        raw = iso.replace("-", "")
        try:
            pool = steep_service.cached_pool(raw)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(pool, dict):
            continue
        up_map: dict[str, int] = defaultdict(int)
        down_map: dict[str, int] = defaultdict(int)
        for row in pool.get("limit_up") or []:
            if not isinstance(row, dict):
                continue
            l3 = mapping.get(_bare6(row.get("code") or "")) or str(row.get("l3_code") or "")
            if l3:
                up_map[l3] += 1
        for row in pool.get("limit_down") or []:
            if not isinstance(row, dict):
                continue
            l3 = mapping.get(_bare6(row.get("code") or "")) or str(row.get("l3_code") or "")
            if l3:
                down_map[l3] += 1
        out[iso] = {"up": dict(up_map), "down": dict(down_map)}
    return out


def _attach_limits(
    rows: list[dict[str, Any]], counts: dict[str, dict[str, int]] | None
) -> None:
    if counts is None:
        return
    up_map = counts.get("up") or {}
    down_map = counts.get("down") or {}
    for row in rows:
        code = str(row.get("code") or "")
        row["limit_up_1d"] = int(up_map.get(code, 0))
        row["limit_down_1d"] = int(down_map.get(code, 0))


def screen_rotation(
    *,
    days: int = DEFAULT_LOOKBACK_DAYS,
    force: bool = False,
    workers: int = KLINE_WORKERS,
) -> dict[str, Any]:
    """近 N 个交易日的三级轮动日历 + 还没涨过名单。"""
    days = clamp_days(days)
    errors: list[str] = []
    industry_service.stocks.ensure_populated()
    stocks = industry_service.stocks.all_stocks()
    index_status = industry_service.get_index_status()
    dates = _trade_dates(days)
    universe = _universe(stocks)

    if not stocks:
        errors.append("股票索引为空，请先打开行业树或个股页让成分股索引建立")
        return {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "window": {"days": days, "start": "", "end": "", "trade_days": 0},
            "universe_count": 0,
            "covered_count": 0,
            "untouched_count": 0,
            "days": [],
            "covered": [],
            "untouched": [],
            "errors": errors,
            "index": index_status,
            "rules": _rules(),
            "note": "没有成分股，无法计算三级行业涨幅",
        }

    by_day: dict[str, tuple[list[dict[str, Any]], str]] = {}
    missing: list[str] = []
    for iso in dates:
        if day_frozen(iso):
            cached = load_l3_day(iso)
            if cached is not None:
                by_day[iso] = cached
                continue
        hit = _day_from_snapshot(iso, force=force)
        if hit is None:
            missing.append(iso)
            continue
        by_day[iso] = hit
        if day_frozen(iso):
            save_l3_day(iso, hit[0], hit[1])

    if missing:
        filled = _backfill_kline(
            missing,
            stocks,
            force=False,
            workers=workers,
            errors=errors,
        )
        for iso in missing:
            rows = filled.get(iso) or []
            if rows:
                by_day[iso] = (rows, _SOURCE_KLINE)
                if day_frozen(iso):
                    save_l3_day(iso, rows, _SOURCE_KLINE)

    dates = [iso for iso in dates if iso in by_day]

    metrics = _current_metrics(stocks, errors)
    limit_maps = _limit_maps(dates, stocks)
    hits: dict[str, list[str]] = defaultdict(list)
    best_score: dict[str, float] = {}
    day_rows: list[dict[str, Any]] = []
    chronological = list(reversed(dates))
    history: dict[str, dict[str, float]] = defaultdict(dict)
    for iso, (rows, _source) in by_day.items():
        for row in rows:
            chg = row.get("change_1d")
            code = str(row.get("code") or "")
            if code and chg is not None:
                history[code][iso] = float(chg)
    for iso in chronological:
        rows, source = by_day.get(iso) or ([], _SOURCE_MISSING)
        _attach_limits(rows, limit_maps.get(iso))
        risen, scored = _pick_named(
            rows,
            iso=iso,
            chronological=chronological,
            history=history,
        )
        for item in scored:
            code = str(item.get("code") or "")
            score = float(item.get("score") or 0)
            if code:
                best_score[code] = max(best_score.get(code, 0.0), score)
        for item in risen:
            hits[item["code"]].append(iso)
        day_rows.append(
            {
                "date": iso,
                "source": source,
                "universe_count": len(rows),
                "risen_count": len(risen),
                "first_count": 0,
                "again_count": 0,
                "first": [],
                "again": [],
                "_risen": risen,
            }
        )
    day_rows.reverse()

    covered: list[dict[str, Any]] = []
    for code, hit_dates in hits.items():
        first = min(hit_dates)
        last = max(hit_dates)
        base = dict(universe.get(code) or {"code": code, "name": code})
        last_day = next(
            (
                item
                for day in day_rows
                for item in (day.get("_risen") or [])
                if item.get("code") == code and day.get("date") == last
            ),
            {},
        )
        covered.append(
            _merge_metrics(
                {
                    **base,
                    "first_date": first,
                    "last_date": last,
                    "hits": len(hit_dates),
                    "leader": last_day.get("leader") or "",
                    "change_1d": last_day.get("change_1d"),
                },
                metrics.get(code),
            )
        )
    covered.sort(
        key=lambda r: (int(r.get("hits") or 0), str(r.get("last_date") or "")),
        reverse=True,
    )

    date_pos = {iso: idx for idx, iso in enumerate(chronological)}
    end_pos = len(chronological) - 1 if chronological else 0
    window_end = chronological[-1] if chronological else ""

    for day in day_rows:
        first_rows: list[dict[str, Any]] = []
        again_rows: list[dict[str, Any]] = []
        for item in day.get("_risen") or []:
            first = min(hits.get(item["code"]) or [day["date"]])
            item["first_date"] = first
            extra = metrics.get(item["code"])
            if extra:
                item["change_5d"] = extra.get("change_5d")
                item["change_ytd"] = extra.get("change_ytd")
                item["main_net"] = extra.get("main_net")
                item["main_net_5d"] = extra.get("main_net_5d")
                item["main_net_10d"] = extra.get("main_net_10d")
            item["hits"] = len([d for d in (hits.get(item["code"]) or []) if d <= day["date"]])
            if day["date"] == first:
                item["tag"] = "首次"
                first_rows.append(item)
            else:
                item["tag"] = "上涨"
                again_rows.append(item)
        day["first"] = first_rows
        day["again"] = again_rows
        day["first_count"] = len(first_rows)
        day["again_count"] = len(again_rows)
        day.pop("_risen", None)

    latest_map: dict[str, dict[str, Any]] = {}
    if window_end:
        latest_rows, _src = by_day.get(window_end) or ([], "")
        for item in latest_rows:
            code = str(item.get("code") or "")
            if code:
                latest_map[code] = item

    ranking: list[dict[str, Any]] = []
    for code, base in universe.items():
        hit_dates = hits.get(code) or []
        last = max(hit_dates) if hit_dates else ""
        first = min(hit_dates) if hit_dates else ""
        if last:
            idle_days = end_pos - date_pos.get(last, end_pos)
        else:
            idle_days = len(chronological)
        row = _merge_metrics(dict(base), metrics.get(code))
        quote = latest_map.get(code)
        if quote:
            for key in (
                "change_1d",
                "up_1d",
                "down_1d",
                "limit_up_1d",
                "limit_down_1d",
                "strong_1d",
                "cap_tier",
                "leader",
            ):
                if quote.get(key) is not None:
                    row[key] = quote.get(key)
        row["hits"] = len(hit_dates)
        row["first_date"] = first
        row["last_date"] = last
        row["idle_days"] = idle_days
        row["score"] = round(best_score.get(code, 0.0), 1)
        ranking.append(row)
    ranking.sort(
        key=lambda r: (-int(r.get("hits") or 0), str(r.get("last_date") or ""), str(r.get("name") or ""))
    )

    untouched: list[dict[str, Any]] = []
    for row in ranking:
        last = str(row.get("last_date") or "")
        if last and last == window_end:
            continue
        item = dict(row)
        tag, reason = _untouched_tag(item)
        if last:
            idle_days = int(item.get("idle_days") or 0)
            item["reason"] = f"距上次上榜 {idle_days} 个交易日（{last}）" + (f"；{reason}" if tag else "")
        elif not tag:
            item["reason"] = "窗口内从未上榜"
        item["tag"] = tag or "待涨"
        untouched.append(item)
    untouched.sort(
        key=lambda r: (-int(r.get("idle_days") or 0), str(r.get("last_date") or ""))
    )

    if not index_status.get("complete"):
        errors.append(
            f"成分股索引未扫完 {index_status.get('l3_covered')}/{index_status.get('l3_total')}，结果可能不全"
        )

    start = chronological[0] if chronological else ""
    end = chronological[-1] if chronological else ""
    note = (
        f"窗口 {days} 个交易日：得分>{SCORE_NAMED:g} 进入当天榜单"
        "（涨幅强度、上涨占比、进攻扩散等权）。"
        "涨幅强度=当日加权涨幅/近20日标准差。"
        "首次=窗口内第一次上榜，记入当天上涨；待涨为窗口内尚未轮到，不随交易日切换。"
        "次数=截至当天的上榜次数。领涨按窗口内上榜总天数排序。"
    )
    return {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "window": {
            "days": days,
            "start": start,
            "end": end,
            "trade_days": len(dates),
        },
        "universe_count": len(universe),
        "covered_count": len(covered),
        "untouched_count": len(untouched),
        "days": day_rows,
        "covered": covered,
        "ranking": ranking,
        "untouched": untouched,
        "errors": errors,
        "index": index_status,
        "rules": _rules(),
        "note": note,
    }


def _rules() -> dict[str, str]:
    return {
        "risen": (
            f"软评分>{SCORE_NAMED:g}，按得分从高到低。"
            "因子：涨幅强度、上涨占比、进攻扩散，三项等权；样本不足"
            f"{MIN_STOCKS}只剔除"
        ),
        "untouched": "待涨：窗口内尚未上榜或距上次最久，不随所选交易日变化",
        "ranking": "领涨：窗口内上榜次数从高到低",
        "watch": "还没过线，但5日和10日资金都在进",
    }


def _drop_closed_days(data: dict[str, Any]) -> dict[str, Any]:
    """去掉没有三级涨跌的休市日，并按剩余交易日重算待涨间隔。"""
    days_in = data.get("days")
    if not isinstance(days_in, list):
        return data
    kept: list[dict[str, Any]] = []
    dropped = False
    for day in days_in:
        if not isinstance(day, dict):
            kept.append(day)
            continue
        empty = not (
            day.get("first")
            or day.get("again")
            or int(day.get("universe_count") or 0)
            or int(day.get("risen_count") or 0)
        )
        if empty and str(day.get("source") or "") in {_SOURCE_MISSING, ""}:
            dropped = True
            continue
        kept.append(day)
    errors_in = [e for e in (data.get("errors") or []) if "无三级涨跌" not in str(e)]
    if not dropped and errors_in == list(data.get("errors") or []):
        return data

    chronological = [str(day.get("date") or "") for day in reversed(kept) if day.get("date")]
    date_pos = {iso: idx for idx, iso in enumerate(chronological)}
    end_pos = len(chronological) - 1 if chronological else 0
    window_end = chronological[-1] if chronological else ""
    untouched: list[dict[str, Any]] = []
    for row in data.get("untouched") or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        last = str(item.get("last_date") or "")
        if last and last == window_end:
            continue
        if last:
            idle_days = end_pos - date_pos.get(last, end_pos)
        else:
            idle_days = len(chronological)
        item["idle_days"] = idle_days
        if last:
            item["reason"] = f"距上次上榜 {idle_days} 个交易日（{last}）"
        untouched.append(item)
    untouched.sort(
        key=lambda r: (-int(r.get("idle_days") or 0), str(r.get("last_date") or ""))
    )

    out = dict(data)
    out["days"] = kept
    out["errors"] = errors_in
    out["untouched"] = untouched
    out["untouched_count"] = len(untouched)
    window = dict(data.get("window") or {})
    window["trade_days"] = len(kept)
    if chronological:
        window["start"] = chronological[0]
        window["end"] = chronological[-1]
    out["window"] = window
    return out


def _fill_day_hits(data: dict[str, Any]) -> None:
    """按交易日累计上榜次数：首次 1，再次 2、3…"""
    days = [day for day in (data.get("days") or []) if isinstance(day, dict)]
    counts: dict[str, int] = defaultdict(int)
    for day in reversed(days):
        for bucket in ("first", "again"):
            filled: list[dict[str, Any]] = []
            for row in day.get(bucket) or []:
                if not isinstance(row, dict):
                    continue
                item = dict(row)
                code = str(item.get("code") or "")
                if code:
                    counts[code] += 1
                    item["hits"] = counts[code]
                filled.append(item)
            day[bucket] = filled


def _ensure_boards(data: dict[str, Any]) -> dict[str, Any]:
    """旧缓存补上次数、统计榜；待涨用最新行情，上涨用当天评分。"""
    ranking = data.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        by_code: dict[str, dict[str, Any]] = {}
        for row in data.get("covered") or []:
            if isinstance(row, dict) and row.get("code"):
                item = dict(row)
                item["hits"] = int(item.get("hits") or 0)
                by_code[str(item["code"])] = item
        for row in data.get("untouched") or []:
            if not isinstance(row, dict) or not row.get("code"):
                continue
            code = str(row["code"])
            if code in by_code:
                continue
            item = dict(row)
            item["hits"] = int(item.get("hits") or 0)
            by_code[code] = item
        ranking = sorted(
            by_code.values(),
            key=lambda r: (
                -int(r.get("hits") or 0),
                str(r.get("last_date") or ""),
                str(r.get("name") or ""),
            ),
        )
        data = dict(data)
        data["ranking"] = ranking
    _fill_day_hits(data)
    quotes = _latest_l3_quotes()
    if not quotes:
        return data
    data = dict(data)
    data["ranking"] = _paint_quotes(data.get("ranking"), quotes)
    if data.get("untouched"):
        data["untouched"] = _paint_quotes(data["untouched"], quotes)
    return data


def apply_top(data: dict[str, Any], top: int | None) -> dict[str, Any]:
    """兼容旧参数：不再截断，大于 60 分全部进榜。"""
    if not isinstance(data, dict):
        return data
    return _ensure_boards(_drop_closed_days(data))
