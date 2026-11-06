"""同花顺个股「五日」分时成交（精确到秒）。

数据口径对齐 App 个股详情里的成交明细（Level-1 约 3 秒快照，时间戳到秒），
覆盖最近 ``n`` 个交易日（默认 5）：

1. **当日**：优先 ``thsdk.list_security_ticks`` 按时间窗拉全日（需已登录）；
   失败则退回 ``quota-h`` ``single_trace``（单次最多约 500 条）。
2. **历史日**：``single_trace`` + ``end_time`` 锚定该日；接口按日只返回
   最近约 500 条，无法再向前翻页，``partial=True`` 标明截断。

交易日列表取自日 K 最近段，避开周末/休市。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float
from company.line.session import parse_session_day, session_day

logger = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=8))
# quota-h single_trace 实测单次有效上限
_TRACE_PAGE = 500
_DEFAULT_DAYS = 5


def _trade_days(code: str, n: int) -> list[str]:
    """最近 ``n`` 个交易日（升序，``YYYY-MM-DD``）。"""
    from company.line.fetcher import fetch_kline

    want = max(1, min(int(n), 20))
    pack = fetch_kline(code, period="day", limit=max(want + 5, 12))
    rows = list(pack.get("items") or [])
    days: list[str] = []
    for row in reversed(rows):
        day = parse_session_day(row.get("time"))
        if day is None:
            continue
        iso = day.isoformat()
        if days and days[-1] == iso:
            continue
        days.append(iso)
        if len(days) >= want:
            break
    days.reverse()
    if days:
        return days
    # 日 K 空时退回日历回推（仅工作日近似）
    cursor = session_day()
    out: list[str] = []
    while len(out) < want:
        if cursor.weekday() < 5:
            out.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    out.reverse()
    return out


def _day_int(iso: str) -> int:
    return int(iso.replace("-", ""))


def _norm_time(value: Any) -> str:
    """统一成 ``YYYY-MM-DD HH:MM:SS``。"""
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) >= 19 and text[4] == "-" and text[10] == " ":
        return text[:19]
    # thsdk: ``YYYYMMDD HH:MM:SS``
    if len(text) >= 17 and text[8] == " " and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]} {text[9:17]}"
    if text.isdigit() and len(text) >= 10:
        try:
            ts = int(text)
            if ts > 10_000_000_000:
                ts //= 1000
            return datetime.fromtimestamp(ts, _TZ).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, OverflowError, ValueError):
            return text
    return text


def _normalize_item(code: str, row: dict[str, Any], *, volume_in_lots: bool) -> dict[str, Any] | None:
    """收成与系统逐笔一致：``volume`` / ``volume_lots`` 均为手。"""
    price = to_float(row.get("price"))
    if price is None:
        return None
    raw_vol = to_float(row.get("volume"))
    if raw_vol is None:
        return None
    if volume_in_lots:
        lots = raw_vol
        shares = raw_vol * 100.0
    else:
        # ths_mobile：volume 为股
        shares = raw_vol
        lots = round(shares / 100.0, 2)
    time_text = _norm_time(row.get("time"))
    if not time_text:
        return None
    stamp = time_text[11:] if len(time_text) >= 19 else str(row.get("stamp") or "")
    amount = to_float(row.get("amount"))
    if amount is None:
        amount = round(price * shares, 2)
    try:
        deal_type = int(float(row.get("deal_type")))
    except (TypeError, ValueError):
        deal_type = -1
    return {
        "time": time_text,
        "stamp": stamp,
        "day": time_text[:10],
        "code": code,
        "price": price,
        "volume": lots,
        "volume_lots": lots,
        "amount": amount,
        "side": row.get("side") or "",
        "side_label": row.get("side_label") or "",
        "deal_type": deal_type,
        "count": row.get("count"),
        "seq": row.get("seq") if row.get("seq") is not None else 0,
        "event_id": row.get("event_id") or f"{time_text}|{lots}|{row.get('seq') or 0}",
    }


def _fetch_day_thsdk(code: str, day: str) -> tuple[list[dict[str, Any]], str]:
    """当日 / 有权限的历史日：thsdk 分片拉全日。"""
    from company.line.tonghuashun.hq_ticks import fetch_time_and_sales

    method, rows = fetch_time_and_sales(code, day=day)
    items: list[dict[str, Any]] = []
    for row in rows:
        parsed = _normalize_item(code, row, volume_in_lots=True)
        if parsed and parsed["day"] == day:
            items.append(parsed)
    items.sort(key=lambda r: (r["time"], int(r.get("seq") or 0)))
    return items, method


def _fetch_day_trace(code: str, day: str) -> tuple[list[dict[str, Any]], str]:
    """``single_trace``：按交易日取最近 ``_TRACE_PAGE`` 条（秒级）。"""
    from company.detail.ths_mobile import fetch_trace

    end = f"{day} 15:30:00"
    rows = fetch_trace(code, count=_TRACE_PAGE, end_time=end)
    if not isinstance(rows, list):
        return [], "ths_mobile:trace"
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _normalize_item(code, row, volume_in_lots=False)
        if parsed and parsed["day"] == day:
            items.append(parsed)
    items.sort(key=lambda r: (r["time"], int(r.get("seq") or 0)))
    return items, "ths_mobile:trace"


def _fetch_day_trend(code: str, day: str) -> list[dict[str, Any]]:
    """同花顺 App 五日图同源：``single_trend`` 分钟点（附带，便于对照）。"""
    from company.detail.ths_mobile import fetch_trend

    raw = fetch_trend(code, trade_date=_day_int(day), trade_class="intraday")
    if not isinstance(raw, list) or not raw:
        return []
    quote = raw[0] if isinstance(raw[0], dict) else {}
    fields = [str(x) for x in (quote.get("data_fields") or [])]
    index = {name: pos for pos, name in enumerate(fields)}
    base_price = to_float(quote.get("base_price"))
    out: list[dict[str, Any]] = []
    prev_cum = None
    for seq, row in enumerate(quote.get("value") or []):
        if not isinstance(row, (list, tuple)):
            continue

        def cell(name: str) -> Any:
            pos = index.get(name)
            if pos is None or pos >= len(row):
                return None
            return row[pos]

        stamp_ms = to_float(cell("1"))
        price = to_float(cell("10"))
        if stamp_ms is None or price is None:
            continue
        cum_vol = to_float(cell("13"))
        cum_amt = to_float(cell("19"))
        vol = None
        if cum_vol is not None and prev_cum is not None:
            vol = cum_vol - prev_cum
        if cum_vol is not None:
            prev_cum = cum_vol
        stamp = datetime.fromtimestamp(stamp_ms / 1000.0, _TZ)
        iso = stamp.strftime("%Y-%m-%d %H:%M:%S")
        if iso[:10] != day:
            continue
        lots = round((vol or 0.0) / 100.0, 2) if vol is not None else None
        out.append(
            {
                "time": iso,
                "stamp": iso[11:],
                "day": day,
                "code": code,
                "price": price,
                "avg_price": None,
                "volume": lots,
                "volume_lots": lots,
                "amount": cum_amt,
                "cum_volume": cum_vol,
                "base_price": base_price,
                "seq": seq,
            }
        )
    return out


def fetch_day(
    code: str,
    day: str | date,
    *,
    prefer_thsdk: bool = True,
    include_trends: bool = True,
) -> dict[str, Any]:
    """单日秒级分时成交。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    parsed = parse_session_day(day)
    if parsed is None:
        raise ValueError(f"无效交易日: {day}")
    iso = parsed.isoformat()
    today = session_day()
    is_today = iso == today.isoformat()
    items: list[dict[str, Any]] = []
    source = ""
    error = ""

    # thsdk 历史窗常 encode_failed / 无权限，仅当日优先走分片全日
    if prefer_thsdk and is_today:
        try:
            items, source = _fetch_day_thsdk(norm, iso)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            logger.info("fivedays thsdk skip %s %s: %s", norm, iso, exc)
            items = []

    if not items:
        try:
            items, source = _fetch_day_trace(norm, iso)
        except Exception as exc:  # noqa: BLE001
            error = error or str(exc)
            logger.info("fivedays trace skip %s %s: %s", norm, iso, exc)
            items, source = [], source or "ths_mobile:trace"

    # quota-h 单日约 500 条封顶，无法日内翻页 → partial
    partial = bool(items) and source.startswith("ths_mobile")
    if source.startswith("thsdk"):
        partial = False

    trends: list[dict[str, Any]] = []
    if include_trends:
        try:
            trends = _fetch_day_trend(norm, iso)
        except Exception as exc:  # noqa: BLE001
            logger.info("fivedays trend skip %s %s: %s", norm, iso, exc)

    out: dict[str, Any] = {
        "code": norm,
        "day": iso,
        "source": source,
        "partial": partial,
        "count": len(items),
        "first": items[0]["time"] if items else "",
        "last": items[-1]["time"] if items else "",
        "items": items,
        "error": error,
    }
    if include_trends:
        out["trend_count"] = len(trends)
        out["trends"] = trends
    return out


def fetch_fivedays(
    code: str,
    *,
    days: int = _DEFAULT_DAYS,
    prefer_thsdk: bool = True,
    include_trends: bool = True,
) -> dict[str, Any]:
    """最近 ``days`` 个交易日的同花顺分时成交（秒级）+ 可选分钟分时。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    day_list = _trade_days(norm, days)
    by_day: dict[str, dict[str, Any]] = {}
    all_items: list[dict[str, Any]] = []
    all_trends: list[dict[str, Any]] = []
    sources: list[str] = []

    for iso in day_list:
        pack = fetch_day(
            norm,
            iso,
            prefer_thsdk=prefer_thsdk,
            include_trends=include_trends,
        )
        day_pack = {
            "day": pack["day"],
            "source": pack["source"],
            "partial": pack["partial"],
            "count": pack["count"],
            "first": pack["first"],
            "last": pack["last"],
            "items": pack["items"],
            "error": pack.get("error") or "",
        }
        if include_trends:
            day_pack["trend_count"] = pack.get("trend_count") or 0
            day_pack["trends"] = pack.get("trends") or []
            all_trends.extend(day_pack["trends"])
        by_day[iso] = day_pack
        all_items.extend(pack["items"])
        if pack["source"]:
            sources.append(pack["source"])

    all_items.sort(key=lambda r: (r["time"], int(r.get("seq") or 0)))
    all_trends.sort(key=lambda r: (r["time"], int(r.get("seq") or 0)))
    uniq_sources = list(dict.fromkeys(sources))

    out: dict[str, Any] = {
        "code": norm,
        "days": day_list,
        "source": "tonghuashun",
        "methods": uniq_sources,
        "count": len(all_items),
        "partial": any(p.get("partial") for p in by_day.values()),
        "first": all_items[0]["time"] if all_items else "",
        "last": all_items[-1]["time"] if all_items else "",
        "items": all_items,
        "by_day": by_day,
    }
    if include_trends:
        out["trend_count"] = len(all_trends)
        out["trends"] = all_trends
    return out
