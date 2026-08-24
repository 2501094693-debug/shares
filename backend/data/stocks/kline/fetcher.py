
"""个股 K 线 / 分时。

数据源策略（东财 push2his 在不少网络会被掐，所以日/周/月先走腾讯）：
- 日 / 周 / 月 / 分钟 K：腾讯优先，东财兜底
- 分时当日：东财 trends2
- 分时五日：东财多日优先；只回一天或不完整时，腾讯 day/query 兜底

对外入口：
- ``fetch_kline(code, period=day|week|month|1m|5m|15m|30m|60m)``
- ``fetch_intraday(code, ndays=1|5)``

HTTP / 代码标识 / 数字解析与盘口共用 ``common.http`` / ``common.codes`` / ``common.fmt``。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from data.stocks.common.cache import TtlCache
from data.stocks.common.codes import secid, tencent_symbol
from data.stocks.common.fmt import to_float
from data.stocks.common.http import get_json
from message.disclosure.http_util import normalize_code

logger = logging.getLogger(__name__)

KLINE_TTL = 120  # 秒；K 线变化慢
INTRADAY_TTL = 20  # 分时更短

_kline_cache = TtlCache(KLINE_TTL)
_intraday_cache = TtlCache(INTRADAY_TTL)

_PERIOD_TO_KLT = {
    "day": "101",
    "d": "101",
    "daily": "101",
    "week": "102",
    "w": "102",
    "weekly": "102",
    "month": "103",
    "m": "103",
    "monthly": "103",
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
}

_KLT_TO_PERIOD = {
    "101": "day",
    "102": "week",
    "103": "month",
    "1": "1m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "60m",
}

_PERIOD_TO_TENCENT = {
    "day": "day",
    "week": "week",
    "month": "month",
}

_PERIOD_TO_TENCENT_MINUTE = {
    "1m": "m1",
    "5m": "m5",
    "15m": "m15",
    "30m": "m30",
    "60m": "m60",
}

_ADJUST_MAP = {
    "0": 0,
    "none": 0,
    "n": 0,
    "1": 1,
    "qfq": 1,
    "forward": 1,
    "2": 2,
    "hfq": 2,
    "backward": 2,
}

_KLINE_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2his.eastmoney.com",
    "https://push2.eastmoney.com",
)

_TREND_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://push2his.eastmoney.com",
)

# 五日分时：push2 / push2delay 常只回当日，历史主机优先
_TREND_HOSTS_MULTI = (
    "https://push2his.eastmoney.com",
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
)

_EM_HEADERS = {"Referer": "https://quote.eastmoney.com/"}


# ---------------------------------------------------------------------------
# 周期 / 复权参数
# ---------------------------------------------------------------------------


def _normalize_period(period: str) -> str:
    key = (period or "day").strip().lower()
    if key not in _PERIOD_TO_KLT:
        raise ValueError(
            "period 须为 day|week|month|1m|5m|15m|30m|60m"
        )
    klt = _PERIOD_TO_KLT[key]
    return _KLT_TO_PERIOD[klt]


def _normalize_adjust(adjust: str | int) -> int:
    key = str(adjust if adjust is not None else "qfq").strip().lower()
    if key not in _ADJUST_MAP:
        raise ValueError("adjust 须为 none|qfq|hfq（或 0|1|2）")
    return _ADJUST_MAP[key]


def _adjust_label(fqt: int) -> str:
    return {0: "none", 1: "qfq", 2: "hfq"}.get(fqt, "none")


# ---------------------------------------------------------------------------
# 东财 K 线
# ---------------------------------------------------------------------------


def _parse_kline_row(line: str) -> dict[str, Any] | None:
    """东财 klines 一行：date,open,close,high,low,volume,amount,..."""
    parts = str(line).split(",")
    if len(parts) < 5:
        return None
    open_ = to_float(parts[1])
    close = to_float(parts[2])
    high = to_float(parts[3])
    low = to_float(parts[4])
    if close is None and open_ is None:
        return None
    item: dict[str, Any] = {
        "time": str(parts[0]).strip(),
        "open": open_,
        "close": close,
        "high": high,
        "low": low,
        "volume": to_float(parts[5]) if len(parts) > 5 else None,
        "amount": to_float(parts[6]) if len(parts) > 6 else None,
    }
    if len(parts) > 7:
        item["amplitude"] = to_float(parts[7])
    if len(parts) > 8:
        item["pct_chg"] = to_float(parts[8])
    if len(parts) > 9:
        item["change"] = to_float(parts[9])
    if len(parts) > 10:
        item["turnover"] = to_float(parts[10])
    return item


def _fetch_eastmoney_kline(
    code: str,
    *,
    period: str,
    adjust: int,
    limit: int,
    beg: str = "",
    end: str = "",
) -> list[dict[str, Any]]:
    """东财日/周/月/分钟 K。多 host 轮询，有一根有效 K 就返回。"""
    klt = _PERIOD_TO_KLT[period]
    params = {
        "secid": secid(code),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": klt,
        "fqt": str(adjust),
        "beg": beg or "19900101",
        "end": end or "20500101",
        "lmt": str(max(1, min(int(limit), 10000))),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    last_exc: Exception | None = None
    for host in _KLINE_HOSTS:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/kline/get",
                params=params,
                headers=_EM_HEADERS,
                timeout=12,
            )
            data = payload.get("data") if isinstance(payload, dict) else None
            klines = (data or {}).get("klines") or [] if isinstance(data, dict) else []
            if not klines:
                continue
            items: list[dict[str, Any]] = []
            for line in klines:
                row = _parse_kline_row(str(line))
                if row:
                    items.append(row)
            if items:
                return items
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.info("eastmoney kline skip %s %s: %s", code, host, exc)
            continue
    if last_exc:
        raise last_exc
    return []


# ---------------------------------------------------------------------------
# 腾讯 K 线（日/周/月 + 分钟）
# ---------------------------------------------------------------------------


def _parse_tencent_row(row: list[Any]) -> dict[str, Any] | None:
    if not isinstance(row, (list, tuple)) or len(row) < 5:
        return None
    open_price = to_float(row[1])
    close = to_float(row[2])
    high = to_float(row[3])
    low = to_float(row[4])
    if close is None and open_price is None:
        return None
    item: dict[str, Any] = {
        "time": str(row[0])[:19].strip(),
        "open": open_price,
        "close": close,
        "high": high,
        "low": low,
        "volume": to_float(row[5]) if len(row) > 5 else None,
        "amount": to_float(row[6]) if len(row) > 6 else None,
    }
    return item


def _format_tencent_minute_time(raw: Any) -> str:
    s = str(raw or "").strip()
    if len(s) >= 12 and s[:12].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    return s


def _fetch_tencent_minute_kline(
    code: str,
    *,
    period: str,
    limit: int,
) -> list[dict[str, Any]]:
    tx_period = _PERIOD_TO_TENCENT_MINUTE.get(period)
    if not tx_period:
        return []
    symbol = tencent_symbol(code)
    payload = get_json(
        "https://ifzq.gtimg.cn/appstock/app/kline/mkline",
        params={"param": f"{symbol},{tx_period},,{limit}"},
        headers={"Referer": "https://gu.qq.com/"},
        timeout=12,
    ) or {}
    node = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get(
        symbol
    ) or {}

    rows = node.get(tx_period) if isinstance(node, dict) else None
    if not isinstance(rows, list):
        return []

    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        open_price = to_float(row[1])
        close = to_float(row[2])
        high = to_float(row[3])
        low = to_float(row[4])
        if close is None and open_price is None:
            continue
        items.append(
            {
                "time": _format_tencent_minute_time(row[0]),
                "open": open_price,
                "close": close,
                "high": high,
                "low": low,
                "volume": to_float(row[5]) if len(row) > 5 else None,
                "amount": None,
            }
        )
    if limit and len(items) > limit:
        items = items[-limit:]
    return items


def _fetch_tencent_kline(
    code: str,
    *,
    period: str,
    adjust: int,
    limit: int,
    beg: str = "",
    end: str = "",
) -> list[dict[str, Any]]:
    """腾讯仅支持 day/week/month；分钟线不走此路径。"""
    tx_period = _PERIOD_TO_TENCENT.get(period)
    if not tx_period:
        return []

    symbol = tencent_symbol(code)

    # 腾讯后复权能力弱；hfq 时仍取不复权，由上层决定是否接受
    qfq_flag = "qfq" if adjust == 1 else ""

    start = ""
    finish = ""
    if beg:
        start = f"{beg[:4]}-{beg[4:6]}-{beg[6:8]}" if len(beg) == 8 else beg
    if end:
        finish = f"{end[:4]}-{end[4:6]}-{end[6:8]}" if len(end) == 8 else end

    if start and finish:
        param = f"{symbol},{tx_period},{start},{finish},{limit},{qfq_flag}"
    else:
        param = f"{symbol},{tx_period},,,{limit},{qfq_flag}"

    payload = get_json(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        params={"param": param},
        headers={"Referer": "https://gu.qq.com/"},
        timeout=12,
    ) or {}

    node = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get(
        symbol
    ) or {}

    if not isinstance(node, dict):
        return []

    rows = None
    if adjust == 1:
        rows = node.get(f"qfq{tx_period}") or node.get("qfqday")
    rows = rows or node.get(tx_period) or node.get("day") or []
    if not isinstance(rows, list):
        return []

    items: list[dict[str, Any]] = []
    for row in rows:
        parsed = _parse_tencent_row(list(row) if isinstance(row, (list, tuple)) else [])
        if parsed:
            items.append(parsed)
    if limit and len(items) > limit:
        items = items[-limit:]

    return items


# ---------------------------------------------------------------------------
# 对外：K 线
# ---------------------------------------------------------------------------


def fetch_kline(
    code: str,
    *,
    period: str = "day",
    adjust: str | int = "qfq",
    limit: int = 320,
    beg: str = "",
    end: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """拉取 K 线。

    period: day|week|month|1m|5m|15m|30m|60m
    adjust: none|qfq|hfq（或 0|1|2），默认前复权。
    日/周/月与分钟都是腾讯优先、东财兜底。
    """
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")

    period = _normalize_period(period)

    fqt = _normalize_adjust(adjust)

    limit = max(1, min(int(limit or 320), 10000))
    beg = (beg or "").replace("-", "").strip()
    end = (end or "").replace("-", "").strip()

    cache_key = f"{code}:{period}:{fqt}:{limit}:{beg}:{end}"
    now = time.time()
    if not force:
        hit = _kline_cache.get(cache_key)
        if hit is not None:
            return hit

    source = ""
    items: list[dict[str, Any]] = []

    # 日/周/月：腾讯优先（东财 push2his 在不少网络会被掐）
    if period in _PERIOD_TO_TENCENT:
        try:
            items = _fetch_tencent_kline(
                code, period=period, adjust=fqt, limit=limit, beg=beg, end=end
            )
            if items:
                source = "tencent"
        except Exception as exc:
            logger.info("tencent kline failed %s: %s", code, exc)
    elif period in _PERIOD_TO_TENCENT_MINUTE:
        try:
            items = _fetch_tencent_minute_kline(code, period=period, limit=limit)
            if items:
                source = "tencent"
        except Exception as exc:
            logger.info("tencent minute kline failed %s: %s", code, exc)

    if not items:
        try:
            items = _fetch_eastmoney_kline(
                code, period=period, adjust=fqt, limit=limit, beg=beg, end=end
            )
            if items:
                source = "eastmoney"
        except Exception as exc:
            logger.info("eastmoney kline failed %s: %s", code, exc)

    result = {
        "code": code,
        "period": period,
        "adjust": _adjust_label(fqt),
        "source": source,
        "count": len(items),
        "items": items,
    }

    _kline_cache.put(cache_key, result, cached_at=now)

    return result


# ---------------------------------------------------------------------------
# 分时（东财 trends2 + 腾讯五日兜底）
# ---------------------------------------------------------------------------


def _parse_trend_row(line: str) -> dict[str, Any] | None:
    # datetime,price,avgPrice,high,low,volume,amount[,...]
    parts = str(line).split(",")
    if len(parts) < 3:
        return None
    price = to_float(parts[1])
    avg = to_float(parts[2])
    if price is None and avg is None:
        return None
    # 部分历史分时 price 可能为 0，用均价兜底
    use_price = price if price not in (None, 0) else avg
    item: dict[str, Any] = {
        "time": str(parts[0]).strip(),
        "price": use_price,
        "avg_price": avg,
        "high": to_float(parts[3]) if len(parts) > 3 else None,
        "low": to_float(parts[4]) if len(parts) > 4 else None,
        "volume": to_float(parts[5]) if len(parts) > 5 else None,
        "amount": to_float(parts[6]) if len(parts) > 6 else None,
    }
    return item


def _trend_unique_days(items: list[dict[str, Any]]) -> int:
    days = {
        str(it.get("time") or "")[:10]
        for it in items
        if str(it.get("time") or "").strip()
    }
    return len(days)


def _fetch_tencent_day_trends(code: str, *, ndays: int = 5) -> dict[str, Any]:
    """腾讯多日分时（day/query），作五日兜底。volume 为当日累计手，需差分。"""
    symbol = tencent_symbol(code)
    payload = get_json(
        "https://web.ifzq.gtimg.cn/appstock/app/day/query",
        params={"code": symbol},
        headers={"Referer": "https://gu.qq.com/"},
        timeout=12,
    ) or {}
    node = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get(
        symbol
    ) or {}
    days = node.get("data") if isinstance(node, dict) else None
    if not isinstance(days, list) or not days:
        return {"items": [], "pre_close": None, "name": ""}

    def _date_key(row: Any) -> str:
        if not isinstance(row, dict):
            return ""
        return str(row.get("date") or "")

    days_sorted = sorted(
        [d for d in days if isinstance(d, dict)],
        key=_date_key,
    )
    if ndays > 0:
        days_sorted = days_sorted[-ndays:]

    items: list[dict[str, Any]] = []
    pre_close: float | None = None
    for day in days_sorted:
        raw_date = str(day.get("date") or "")
        if len(raw_date) == 8 and raw_date.isdigit():
            date_fmt = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        else:
            date_fmt = raw_date
        prec = to_float(day.get("prec"))
        if pre_close is None and prec is not None:
            pre_close = prec

        prev_vol = 0.0
        prev_amt = 0.0
        for line in day.get("data") or []:
            parts = str(line).split()
            if len(parts) < 3:
                continue
            hm = parts[0].zfill(4)
            if len(hm) < 4 or not hm.isdigit():
                continue
            # 主会话到 15:00，去掉盘后零碎点
            if hm > "1500":
                continue
            price = to_float(parts[1])
            cum_vol = to_float(parts[2]) or 0.0
            cum_amt = to_float(parts[3]) if len(parts) > 3 else None
            vol = max(0.0, cum_vol - prev_vol)
            prev_vol = cum_vol
            amount = None
            if cum_amt is not None:
                amount = max(0.0, cum_amt - prev_amt)
                prev_amt = cum_amt
            avg = None
            if cum_amt is not None and cum_vol > 0:
                avg = cum_amt / (cum_vol * 100.0)
            items.append(
                {
                    "time": f"{date_fmt} {hm[:2]}:{hm[2:4]}",
                    "price": price,
                    "avg_price": avg if avg is not None else price,
                    "high": price,
                    "low": price,
                    "volume": vol,
                    "amount": amount,
                }
            )

    name = ""
    qt = node.get("qt") if isinstance(node, dict) else None
    if isinstance(qt, dict):
        # qt 结构因股票而异，尽量取简称
        for key in (symbol, f"q{symbol}", "name"):
            val = qt.get(key)
            if isinstance(val, list) and len(val) > 1:
                name = str(val[1] or "").strip()
                if name:
                    break
            if isinstance(val, str) and val.strip():
                name = val.strip()
                break

    return {"items": items, "pre_close": pre_close, "name": name}


def fetch_intraday(
    code: str,
    *,
    ndays: int = 1,
    force: bool = False,
) -> dict[str, Any]:
    """拉取分时。``ndays=1`` 当日，``ndays=5`` 五日。

    五日时东财部分 host 只回当天，会继续试 push2his；仍不够再走腾讯 day/query。
    """
    code = normalize_code(code)
    if not code:
        raise ValueError("无效股票代码")

    ndays = int(ndays or 1)
    if ndays not in (1, 5):
        raise ValueError("ndays 须为 1 或 5")

    cache_key = f"{code}:{ndays}"
    now = time.time()
    if not force:
        hit = _intraday_cache.get(cache_key)
        if hit is not None:
            return hit

    params = {
        "secid": secid(code),
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "iscr": "0",
        "ndays": str(ndays),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }

    items: list[dict[str, Any]] = []
    pre_close: float | None = None
    name = ""
    source = ""
    last_exc: Exception | None = None
    best: tuple[int, int, list[dict[str, Any]], float | None, str] | None = None

    hosts = _TREND_HOSTS_MULTI if ndays > 1 else _TREND_HOSTS
    for host in hosts:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/trends2/get",
                params=params,
                headers=_EM_HEADERS,
                timeout=10,
            )
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                continue
            trends = data.get("trends") or []

            parsed: list[dict[str, Any]] = []
            for line in trends:
                row = _parse_trend_row(str(line))
                if row:
                    parsed.append(row)
            if not parsed:
                continue

            day_n = _trend_unique_days(parsed)
            # 五日请求若某主机只回一天，记为候选但继续试更好源
            if ndays > 1 and day_n < 2:
                logger.info(
                    "eastmoney intraday incomplete %s host=%s days=%s n=%s",
                    code,
                    host,
                    day_n,
                    len(parsed),
                )
                score = (day_n, len(parsed))
                if best is None or score > (best[0], best[1]):
                    best = (
                        day_n,
                        len(parsed),
                        parsed,
                        to_float(data.get("preClose")) or to_float(data.get("prePrice")),
                        str(data.get("name") or "").strip(),
                    )
                continue

            items = parsed
            pre_close = to_float(data.get("preClose")) or to_float(data.get("prePrice"))
            name = str(data.get("name") or "").strip()
            source = "eastmoney"
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.info("eastmoney intraday skip %s %s: %s", code, host, exc)
            continue

    # 五日：东财常被掐或不完整时，用腾讯多日分时
    need_tencent = ndays > 1 and (
        not items or _trend_unique_days(items) < min(ndays, 3)
    )
    if need_tencent:
        try:
            tx = _fetch_tencent_day_trends(code, ndays=ndays)
            tx_items = tx.get("items") or []
            if _trend_unique_days(tx_items) >= 2:
                items = tx_items
                pre_close = tx.get("pre_close")
                name = str(tx.get("name") or name or "").strip()
                source = "tencent"
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.info("tencent multi-day intraday failed %s: %s", code, exc)

    if not items and best is not None:
        _, _, items, pre_close, name = best
        source = "eastmoney"

    if not items and last_exc and not source:
        logger.warning("intraday empty %s: %s", code, last_exc)

    result = {
        "code": code,
        "name": name,
        "ndays": ndays,
        "pre_close": pre_close,
        "source": source,
        "count": len(items),
        "items": items,
    }
    _intraday_cache.put(cache_key, result, cached_at=now)
    return result
