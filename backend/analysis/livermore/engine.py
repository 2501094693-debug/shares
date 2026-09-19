"""单标的诊断：指数 / 个股。"""

from __future__ import annotations

import logging
from typing import Any

from analysis.livermore.action import decide_action
from analysis.livermore.atr import last_atr
from analysis.livermore.bars import align_by_date, mean_amount, parse_bars
from analysis.livermore.config import (
    INDEX_CODE,
    INDEX_NAME,
    KLINE_LIMIT,
    LIVE_AMOUNT,
    LIVE_ATR_PCT,
    MIN_BARS,
    RS_DAYS,
    RULESET,
    VOLUME_LOOKBACK,
)
from analysis.livermore.follow import follow_through
from analysis.livermore.gate import market_gate
from analysis.livermore.key import walk_key
from analysis.livermore.pivot import detect_pivots
from analysis.livermore.strength import change_nd, rank_in_group, vs_benchmark
from analysis.livermore.volume import volume_state
from company.line.fetcher import fetch_kline
from core.codes import normalize_code

logger = logging.getLogger(__name__)


def _fetch_index_pack() -> dict[str, Any]:
    """上证指数。必须带 SH 前缀，否则会被收成平安银行。"""
    try:
        from company.line.tencent_kline import fetch_line as fetch_tencent
        pack = fetch_tencent(INDEX_CODE, period="day", adjust="none", limit=KLINE_LIMIT)
        if pack.get("items"):
            return pack
    except Exception as exc:  # noqa: BLE001
        logger.info("index tencent skip: %s", exc)
    try:
        from company.line.eastmoney_kline import fetch_line as fetch_eastmoney
        pack = fetch_eastmoney(INDEX_CODE, period="day", adjust="none", limit=KLINE_LIMIT)
        if pack.get("items"):
            return pack
    except Exception as exc:  # noqa: BLE001
        logger.info("index eastmoney skip: %s", exc)
    return {}


def analyze_bars(
    bars: list[dict[str, Any]],
    raw_bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """只对日 K 走六栏 / 关键点 / 量能，不含行业闸门。"""
    qfq, raw = align_by_date(bars, raw_bars)
    key_state = walk_key(qfq)
    atr = last_atr(qfq)
    close = qfq[-1]["close"] if qfq else None
    pivots = detect_pivots(qfq, raw, atr or 0.0, key_state) if atr else []
    volume = volume_state(qfq, pivots)
    follow = follow_through(qfq, pivots, atr or 0.0)
    atr_pct = None
    if atr and close:
        atr_pct = round(atr / close * 100.0, 3)
    amount = mean_amount(qfq, VOLUME_LOOKBACK)
    live = bool(atr_pct is not None and atr_pct >= LIVE_ATR_PCT)
    if amount is not None and amount < LIVE_AMOUNT:
        live = False
    liveliness = "live" if live else "dead"
    return {
        "as_of": qfq[-1]["date"] if qfq else "",
        "close": close,
        "atr": round(atr, 4) if atr else None,
        "atr_pct": atr_pct,
        "avg_amount": round(amount, 1) if amount else None,
        "liveliness": liveliness,
        "key": key_state,
        "pivotal": pivots,
        "volume": volume,
        "follow": follow,
        "change_20d": change_nd(qfq, RS_DAYS),
        "bar_count": len(qfq),
    }


def analyze_index() -> dict[str, Any]:
    pack = _fetch_index_pack()
    bars = parse_bars(list(pack.get("items") or []))
    tape = analyze_bars(bars, bars)
    gate = market_gate(tape.get("key"))
    return {
        "code": INDEX_CODE,
        "name": pack.get("name") or INDEX_NAME,
        "source": pack.get("source") or "",
        **tape,
        "gate": gate,
        "ruleset": RULESET,
    }


def _fetch_stock_bars(code: str, *, fetch_raw: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    pack = fetch_kline(code, period="day", adjust="qfq", limit=KLINE_LIMIT)
    qfq = parse_bars(list(pack.get("items") or []))
    raw = qfq
    if fetch_raw:
        try:
            raw_pack = fetch_kline(code, period="day", adjust="none", limit=KLINE_LIMIT)
            raw = parse_bars(list(raw_pack.get("items") or [])) or qfq
        except Exception as exc:  # noqa: BLE001
            logger.info("raw kline skip %s: %s", code, exc)
    return qfq, raw, str(pack.get("name") or ""), str(pack.get("source") or "")


def tape_from_meta(
    meta: dict[str, Any],
    *,
    fetch_raw: bool = False,
) -> dict[str, Any]:
    code = normalize_code(str(meta.get("code") or ""))
    base = {
        "code": code,
        "name": meta.get("name") or "",
        "l1_name": meta.get("l1_name") or "",
        "l2_name": meta.get("l2_name") or "",
        "l3_name": meta.get("l3_name") or "",
        "l3_code": meta.get("l3_code") or "",
    }
    if not code:
        return {**base, "error": "无效代码"}
    try:
        qfq, raw, name, source = _fetch_stock_bars(code, fetch_raw=fetch_raw)
    except Exception as exc:  # noqa: BLE001
        return {**base, "error": str(exc)}
    if name:
        base["name"] = name
    if len(qfq) < MIN_BARS:
        return {**base, "error": "日 K 不足", "kline_source": source, "bar_count": len(qfq)}
    tape = analyze_bars(qfq, raw)
    return {
        **base,
        **tape,
        "kline_source": source,
        "ruleset": RULESET,
    }


def apply_context(
    tape: dict[str, Any],
    *,
    index_snap: dict[str, Any] | None,
    peer_changes: list[float],
    industry_leading: bool,
    industry_tag: str = "",
) -> dict[str, Any]:
    """叠加大盘闸门、组内排名，给出 action。"""
    if tape.get("error"):
        return tape
    gate = (index_snap or {}).get("gate") or market_gate((index_snap or {}).get("key"))
    index_chg = (index_snap or {}).get("change_20d")
    stock_chg = tape.get("change_20d")
    rs = rank_in_group(stock_chg, peer_changes)
    vs_index = vs_benchmark(stock_chg, index_chg)
    vs_l3 = vs_benchmark(stock_chg, _median(peer_changes))
    key_state = tape.get("key") or {}
    rs_ok = bool(rs.get("leader")) if rs.get("rank") is not None else True
    decided = decide_action(
        gate=gate,
        key_state=key_state,
        pivots=list(tape.get("pivotal") or []),
        volume=tape.get("volume") or {},
        follow=tape.get("follow") or {},
        liveliness=str(tape.get("liveliness") or "dead"),
        industry_leading=industry_leading,
        rs_leader=rs_ok,
        atr=tape.get("atr"),
        close=tape.get("close"),
    )
    return {
        **tape,
        "gate": gate,
        "industry": {
            "l3_name": tape.get("l3_name") or "",
            "l3_code": tape.get("l3_code") or "",
            "leading": industry_leading,
            "tag": industry_tag,
        },
        "rs": {
            "vs_index_20d": vs_index,
            "vs_l3_20d": vs_l3,
            **rs,
        },
        **decided,
        "column": key_state.get("column"),
        "column_label": key_state.get("column_label"),
        "ruleset": RULESET,
    }


def _median(values: list[float]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    nums.sort()
    mid = len(nums) // 2
    if len(nums) % 2:
        return nums[mid]
    return (nums[mid - 1] + nums[mid]) / 2.0


def analyze_stock(
    code: str,
    *,
    meta: dict[str, Any] | None = None,
    fetch_raw: bool = True,
    index_snap: dict[str, Any] | None = None,
    peer_changes: list[float] | None = None,
    industry_leading: bool = True,
    industry_tag: str = "",
) -> dict[str, Any]:
    row = dict(meta or {})
    row["code"] = code
    tape = tape_from_meta(row, fetch_raw=fetch_raw)
    if index_snap is None:
        try:
            index_snap = analyze_index()
        except Exception as exc:  # noqa: BLE001
            logger.info("index snap skip: %s", exc)
            index_snap = {"gate": market_gate(None), "change_20d": None}
    return apply_context(
        tape,
        index_snap=index_snap,
        peer_changes=list(peer_changes or []),
        industry_leading=industry_leading,
        industry_tag=industry_tag,
    )
