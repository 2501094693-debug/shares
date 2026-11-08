"""同花顺分时成交（``single_trend`` 分钟级）。

按交易日拉整段分时（约 240 点/天，含价格 / 均价基准 / 累计量），支持单日与最近
``n`` 个交易日。与同花顺 App「分时 / 五日」图同源，免登录，历史可回溯多年。

这里只保留「分时成交」能力；逐笔明细（``single_trace`` 尾盘 500 笔那套）已删除。

    python -m company.line.tonghuashun.intraday 600519
    python -m company.line.tonghuashun.intraday 000338 --days 5
    python -m company.line.tonghuashun.intraday 000338 --day 2026-11-05
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __name__ == "__main__" or __package__:
    _BACKEND = Path(__file__).resolve().parents[3]
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))

from core.codes import normalize_code
from core.fmt import to_float
from company.line.session import parse_session_day, session_day

logger = logging.getLogger(__name__)

_TZ = timezone(timedelta(hours=8))
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


def _fetch_day_trend(code: str, day: str) -> list[dict[str, Any]]:
    """``single_trend`` 分钟点（与 App 分时 / 五日图同源）。"""
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
        # 累计量差分 → 本分钟量；首根没有 prev，整段累计即开盘量
        vol_shares = None
        if cum_vol is not None:
            vol_shares = cum_vol if prev_cum is None else cum_vol - prev_cum
            prev_cum = cum_vol
        stamp = datetime.fromtimestamp(stamp_ms / 1000.0, _TZ)
        iso = stamp.strftime("%Y-%m-%d %H:%M:%S")
        if iso[:10] != day:
            continue
        lots = (
            round(vol_shares / 100.0, 2)
            if vol_shares is not None
            else None
        )
        # 分时均价 = 累计额 / 累计量（与 App 五日图橙色均线一致）
        avg_price = None
        if cum_amt is not None and cum_vol is not None and cum_vol > 0:
            avg_price = round(cum_amt / cum_vol, 4)
        out.append(
            {
                "time": iso,
                "stamp": iso[11:],
                "day": day,
                "code": code,
                "price": price,
                "avg_price": avg_price,
                "volume": lots,
                "volume_lots": lots,
                "amount": cum_amt,
                "cum_volume": cum_vol,
                "base_price": base_price,
                "seq": seq,
            }
        )
    return out


def fetch_day_trend(code: str, day: str | Any) -> dict[str, Any]:
    """单日分时成交（分钟级）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    parsed = parse_session_day(day)
    if parsed is None:
        raise ValueError(f"无效交易日: {day}")
    iso = parsed.isoformat()
    trends: list[dict[str, Any]] = []
    error = ""
    try:
        trends = _fetch_day_trend(norm, iso)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        logger.info("intraday trend skip %s %s: %s", norm, iso, exc)
    return {
        "code": norm,
        "day": iso,
        "source": "ths_mobile:trend" if trends else "",
        "count": len(trends),
        "first": trends[0]["time"] if trends else "",
        "last": trends[-1]["time"] if trends else "",
        "trends": trends,
        "error": error,
    }


def fetch_intraday(code: str, *, days: int = _DEFAULT_DAYS) -> dict[str, Any]:
    """最近 ``days`` 个交易日的分时成交（分钟级）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    day_list = _trade_days(norm, days)
    by_day: dict[str, dict[str, Any]] = {}
    all_trends: list[dict[str, Any]] = []

    for iso in day_list:
        trends: list[dict[str, Any]] = []
        error = ""
        try:
            trends = _fetch_day_trend(norm, iso)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            logger.info("intraday trend skip %s %s: %s", norm, iso, exc)
        by_day[iso] = {
            "day": iso,
            "source": "ths_mobile:trend" if trends else "",
            "count": len(trends),
            "first": trends[0]["time"] if trends else "",
            "last": trends[-1]["time"] if trends else "",
            "trends": trends,
            "error": error,
        }
        all_trends.extend(trends)

    all_trends.sort(key=lambda r: (r["time"], int(r.get("seq") or 0)))
    return {
        "code": norm,
        "days": day_list,
        "source": "tonghuashun",
        "count": len(all_trends),
        "first": all_trends[0]["time"] if all_trends else "",
        "last": all_trends[-1]["time"] if all_trends else "",
        "trends": all_trends,
        "by_day": by_day,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="同花顺分时成交（分钟级）")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--days", type=int, default=_DEFAULT_DAYS, help="交易日数，默认 5")
    parser.add_argument("--day", default="", help="只拉单日，如 2026-11-05")
    parser.add_argument("--limit", type=int, default=5, help="预览每段首尾条数，0=全量")
    args = parser.parse_args()

    if args.day:
        pack = fetch_day_trend(args.code, args.day)
    else:
        pack = fetch_intraday(args.code, days=args.days)

    if args.limit == 0:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
        return 0 if pack.get("count") else 1

    items = list(pack.get("trends") or [])
    n = max(0, args.limit)
    summary = {
        "code": pack.get("code"),
        "days": pack.get("days") or [pack.get("day")],
        "source": pack.get("source"),
        "count": pack.get("count"),
        "first": pack.get("first"),
        "last": pack.get("last"),
    }
    if "by_day" in pack:
        summary["by_day"] = {
            day: {
                "count": info.get("count"),
                "first": info.get("first"),
                "last": info.get("last"),
                "error": info.get("error") or None,
            }
            for day, info in (pack.get("by_day") or {}).items()
        }
    else:
        summary["day"] = pack.get("day")
        summary["error"] = pack.get("error") or None
    if n and items:
        summary["preview_head"] = items[:n]
        tail = items[-n:] if len(items) > n else []
        if tail and tail[0] != items[0]:
            summary["preview_tail"] = tail
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
