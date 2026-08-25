"""腾讯 ``fqkline`` / ``mkline`` K 线接入。

日 / 周 / 月：``https://web.ifzq.gtimg.cn/appstock/app/fqkline/get``
- param: ``sh600519,day,start,end,limit,qfq``
- 周期：day / week / month
- 复权：空=不复权，``qfq`` 前复权，``hfq`` 后复权（指数通常只有不复权）

分钟：``https://ifzq.gtimg.cn/appstock/app/kline/mkline``
- param: ``sh600519,m5,,limit``
- 周期：m1 / m5 / m15 / m30 / m60
- 分钟线不复权，也不按日期区间过滤

腾讯没有季 / 半年 / 年 / 120 分钟。个股日 K 常见上限约 640 根。

    python company/line/tencent_kline.py 600519
    python company/line/tencent_kline.py sh000001 --period day --limit 5
    python company/line/tencent_kline.py 000001 --period week
    python company/line/tencent_kline.py 600519 --period 5m --limit 10
    python company/line/tencent_kline.py 600519 --period day --beg 20240101 --end 20241231
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import tencent_symbol as _stock_symbol
from core.fmt import to_float
from core.http import get_json

logger = logging.getLogger(__name__)

# 规范名 → 腾讯 period。只收录接口真正支持的。
PERIOD_TX: dict[str, str] = {
    "1m": "m1",
    "5m": "m5",
    "15m": "m15",
    "30m": "m30",
    "60m": "m60",
    "day": "day",
    "week": "week",
    "month": "month",
}

MINUTE_PERIODS: tuple[str, ...] = ("1m", "5m", "15m", "30m", "60m")
BAR_PERIODS: tuple[str, ...] = ("day", "week", "month")
ALL_PERIODS: tuple[str, ...] = MINUTE_PERIODS + BAR_PERIODS
DEFAULT_PERIODS: tuple[str, ...] = ("day", "week", "month")

_PERIOD_ALIASES: dict[str, str] = {
    "1": "1m",
    "1m": "1m",
    "1min": "1m",
    "min1": "1m",
    "5": "5m",
    "5m": "5m",
    "5min": "5m",
    "15": "15m",
    "15m": "15m",
    "15min": "15m",
    "30": "30m",
    "30m": "30m",
    "30min": "30m",
    "60": "60m",
    "60m": "60m",
    "60min": "60m",
    "1h": "60m",
    "hour": "60m",
    "day": "day",
    "d": "day",
    "daily": "day",
    "101": "day",
    "week": "week",
    "w": "week",
    "weekly": "week",
    "102": "week",
    "month": "month",
    "m": "month",
    "monthly": "month",
    "103": "month",
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

_FQKLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_MKLINE_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
_HEADERS = {"Referer": "https://gu.qq.com/"}
_MAX_LMT = 10000

_PREFIX_MARKET = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
_SSE_HEADS = ("50", "51", "52", "56", "58", "60", "68")
_SZSE_HEADS = ("00", "15", "16", "18", "20", "30", "39")

_TX_RE = re.compile(r"^(sh|sz|bj|hk)[0-9a-z]+$", re.I)
_SECID_RE = re.compile(r"^(\d+)\.(\d{6})$")
_PREFIX_RE = re.compile(r"^(SH|SZ|BJ)(\d{6})$", re.I)
_SUFFIX_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$", re.I)


def _normalize_period(period: str) -> str:
    key = (period or "day").strip().lower()
    if key in ("120", "120m", "2h"):
        raise ValueError("腾讯不支持 120 分钟 K 线")
    if key in ("104", "quarter", "q", "season", "qtr"):
        raise ValueError("腾讯不支持季 K")
    if key in ("105", "halfyear", "half", "hy", "h", "semiannual"):
        raise ValueError("腾讯不支持半年 K")
    if key in ("106", "year", "y", "yearly", "annual"):
        raise ValueError("腾讯不支持年 K")
    if key in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[key]
    if key in PERIOD_TX:
        return key
    raise ValueError("period 须为 1m|5m|15m|30m|60m|day|week|month")


def _normalize_adjust(adjust: str | int) -> int:
    key = str(adjust if adjust is not None else "qfq").strip().lower()
    if key not in _ADJUST_MAP:
        raise ValueError("adjust 须为 none|qfq|hfq（或 0|1|2）")
    return _ADJUST_MAP[key]


def _adjust_label(fqt: int) -> str:
    return {0: "none", 1: "qfq", 2: "hfq"}.get(fqt, "none")


def _fq_flag(fqt: int) -> str:
    return {0: "", 1: "qfq", 2: "hfq"}.get(fqt, "")


def _normalize_date(value: str) -> str:
    text = (value or "").replace("-", "").replace("/", "").strip()
    if not text:
        return ""
    if text in ("0", "1"):
        return text
    if len(text) == 8 and text.isdigit():
        return text
    raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")


def _ymd(value: str) -> str:
    if not value or value in ("0", "1"):
        return ""
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def resolve_symbol(code: str) -> str:
    """把各种写法收成腾讯代码，例如 ``sh600519`` / ``sz000001``。

    ``SH000001`` 是上证指数，``000001`` / ``SZ000001`` 是平安银行。
    已是 ``sh600519`` 则原样（小写）返回。
    """
    raw = (code or "").strip()
    if not raw:
        return ""
    if _TX_RE.match(raw):
        return raw.lower()
    compact = raw.upper().replace(" ", "")
    prefixed = _PREFIX_RE.match(compact)
    if prefixed:
        return f"{_PREFIX_MARKET[prefixed.group(1)]}{prefixed.group(2)}"
    suffixed = _SUFFIX_RE.match(compact)
    if suffixed:
        return f"{_PREFIX_MARKET[suffixed.group(2)]}{suffixed.group(1)}"
    secid = _SECID_RE.match(raw)
    if secid:
        prefix = "sh" if secid.group(1) == "1" else "sz"
        return f"{prefix}{secid.group(2)}"
    digits = re.sub(r"[^0-9]", "", raw)
    if len(digits) == 6:
        if digits.startswith(_SSE_HEADS):
            return f"sh{digits}"
        if digits.startswith(_SZSE_HEADS):
            return f"sz{digits}"
        if digits.startswith(("8", "4", "92")):
            return f"bj{digits}"
    return _stock_symbol(raw)


def _format_minute_time(raw: Any) -> str:
    s = str(raw or "").strip()
    if len(s) >= 12 and s[:12].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    return s


def _parse_row(row: Any, *, minute: bool = False) -> dict[str, Any] | None:
    if not isinstance(row, (list, tuple)) or len(row) < 5:
        return None
    open_ = to_float(row[1])
    close = to_float(row[2])
    high = to_float(row[3])
    low = to_float(row[4])
    if close is None and open_ is None:
        return None
    time_s = _format_minute_time(row[0]) if minute else str(row[0])[:19].strip()
    amount = None
    if len(row) > 6 and not isinstance(row[6], dict):
        amount = to_float(row[6])
    return {
        "time": time_s,
        "open": open_,
        "close": close,
        "high": high,
        "low": low,
        "volume": to_float(row[5]) if len(row) > 5 else None,
        "amount": amount,
    }


def _fill_change(items: list[dict[str, Any]]) -> None:
    """用上一根收盘补涨跌额 / 涨跌幅 / 振幅。"""
    prev: float | None = None
    for item in items:
        close = to_float(item.get("close"))
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        if prev not in (None, 0) and close is not None:
            item["change"] = round(close - prev, 4)
            item["pct_chg"] = round((close / prev - 1.0) * 100, 4)
            if high is not None and low is not None:
                item["amplitude"] = round((high - low) / prev * 100, 4)
        prev = close if close is not None else prev


def _extract_name(node: dict[str, Any], symbol: str) -> str:
    qt = node.get("qt")
    if not isinstance(qt, dict):
        return ""
    for key in (symbol, f"q{symbol}", "name"):
        val = qt.get(key)
        if isinstance(val, list) and len(val) > 1:
            name = str(val[1] or "").strip()
            if name:
                return name
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _pick_bar_rows(node: dict[str, Any], tx_period: str, fqt: int) -> list[Any]:
    keys: list[str] = []
    if fqt == 1:
        keys.append(f"qfq{tx_period}")
    elif fqt == 2:
        keys.append(f"hfq{tx_period}")
    keys.extend((tx_period, "day", "qfqday", "hfqday"))
    for key in keys:
        rows = node.get(key)
        if isinstance(rows, list) and rows:
            return rows
    return []


def _request(url: str, param: str) -> dict[str, Any]:
    payload = get_json(
        url,
        params={"param": param},
        headers=_HEADERS,
        timeout=12,
    ) or {}
    return payload if isinstance(payload, dict) else {}


def fetch_line(
    code: str,
    *,
    period: str = "day",
    adjust: str | int = "qfq",
    limit: int = 320,
    beg: str = "",
    end: str = "",
) -> dict[str, Any]:
    """从腾讯拉一根周期的 K 线。

    period: 1m|5m|15m|30m|60m|day|week|month
    adjust: none|qfq|hfq（或 0|1|2），默认前复权；分钟线忽略复权。
    不传 ``beg`` 时按最近 ``limit`` 根拉；传了 ``beg`` 则按日期区间（仅日/周/月）。
    """
    symbol = resolve_symbol(code)
    if not symbol:
        raise ValueError("无效股票代码")

    period = _normalize_period(period)
    tx_period = PERIOD_TX[period]
    fqt = _normalize_adjust(adjust)
    cap = int(limit) if limit is not None else 320
    if cap <= 0:
        cap = _MAX_LMT
    cap = max(1, min(cap, _MAX_LMT))
    beg = _normalize_date(beg)
    end = _normalize_date(end)
    minute = period in PERIOD_TX and period in MINUTE_PERIODS
    query = "range" if beg and not minute else "last"

    name = ""
    items: list[dict[str, Any]] = []
    used_adjust = "none" if minute else _adjust_label(fqt)

    try:
        if minute:
            payload = _request(_MKLINE_URL, f"{symbol},{tx_period},,{cap}")
            node = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get(
                symbol
            ) or {}
            if isinstance(node, dict):
                name = _extract_name(node, symbol)
                rows = node.get(tx_period) or []
                if isinstance(rows, list):
                    for row in rows:
                        parsed = _parse_row(row, minute=True)
                        if parsed:
                            items.append(parsed)
        else:
            start = _ymd(beg)
            finish = _ymd(end)
            fq = _fq_flag(fqt)
            if start and finish:
                param = f"{symbol},{tx_period},{start},{finish},{cap},{fq}"
            elif start:
                param = f"{symbol},{tx_period},{start},,{cap},{fq}"
            elif finish:
                param = f"{symbol},{tx_period},,{finish},{cap},{fq}"
            else:
                param = f"{symbol},{tx_period},,,{cap},{fq}"
            payload = _request(_FQKLINE_URL, param)
            node = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get(
                symbol
            ) or {}
            if isinstance(node, dict):
                name = _extract_name(node, symbol)
                for row in _pick_bar_rows(node, tx_period, fqt):
                    parsed = _parse_row(row, minute=False)
                    if parsed:
                        items.append(parsed)
    except Exception:
        logger.exception("tencent line failed %s %s", symbol, period)
        raise

    if query == "range" and items:
        lo = _ymd(beg)
        hi = _ymd(end)
        clipped: list[dict[str, Any]] = []
        for item in items:
            day = str(item.get("time") or "")[:10]
            if lo and day < lo:
                continue
            if hi and day > hi:
                continue
            clipped.append(item)
        items = clipped
    elif cap and len(items) > cap:
        items = items[-cap:]

    _fill_change(items)
    digits = re.sub(r"[^0-9]", "", symbol) or symbol

    return {
        "code": digits,
        "symbol": symbol,
        "name": name,
        "period": period,
        "tx_period": tx_period,
        "adjust": used_adjust,
        "query": query,
        "source": "tencent" if items else "",
        "count": len(items),
        "items": items,
    }


def fetch_lines(
    code: str,
    *,
    periods: tuple[str, ...] | list[str] | None = None,
    adjust: str | int = "qfq",
    limit: int = 320,
    beg: str = "",
    end: str = "",
) -> dict[str, Any]:
    """并行拉取多个周期。默认日 / 周 / 月。"""
    symbol = resolve_symbol(code)
    if not symbol:
        raise ValueError("无效股票代码")

    chosen = tuple(periods) if periods else DEFAULT_PERIODS
    canon = [_normalize_period(p) for p in chosen]
    fqt = _normalize_adjust(adjust)

    result: dict[str, Any] = {
        "code": "",
        "symbol": symbol,
        "name": "",
        "adjust": _adjust_label(fqt),
        "source": "tencent",
    }

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(canon)))) as pool:
        futs = {
            period: pool.submit(
                fetch_line,
                code,
                period=period,
                adjust=fqt,
                limit=limit,
                beg=beg,
                end=end,
            )
            for period in canon
        }
        for period, fut in futs.items():
            result[period] = fut.result()

    for period in canon:
        pack = result.get(period) or {}
        if pack.get("name") or pack.get("code"):
            result["name"] = pack.get("name") or result["name"]
            result["code"] = pack.get("code") or result["code"]
            break
    if not result["code"]:
        result["code"] = re.sub(r"[^0-9]", "", symbol) or symbol
    return result


def _print_preview(pack: dict[str, Any], preview: int) -> None:
    items = pack.get("items") or []
    print(
        f"  {pack.get('period')}({pack.get('tx_period')})  "
        f"{pack.get('name') or ''}  count={pack.get('count')}  "
        f"query={pack.get('query')}  source={pack.get('source')}"
    )
    if not items:
        print("  (empty)")
        return
    shown = items[-preview:] if preview > 0 else items
    print(json.dumps(shown, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="从腾讯拉取 K 线")
    parser.add_argument(
        "code",
        nargs="?",
        default="600519",
        help="代码或腾讯代码，如 600519 / sh000001 / SZ000001",
    )
    parser.add_argument(
        "--period",
        default="bars",
        help="周期，或 bars(日周月) / minutes(全部分钟)",
    )
    parser.add_argument("--adjust", default="qfq", help="none|qfq|hfq，默认前复权")
    parser.add_argument("--limit", type=int, default=5, help="最近根数")
    parser.add_argument("--beg", default="", help="起始日 YYYYMMDD，仅日/周/月")
    parser.add_argument("--end", default="", help="结束日 YYYYMMDD")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    key = (args.period or "bars").strip().lower()
    if key in ("bars", "dwm", "default", "all", "*"):
        chosen: tuple[str, ...] = DEFAULT_PERIODS
    elif key in ("minutes", "minute", "min"):
        chosen = MINUTE_PERIODS
    else:
        chosen = (_normalize_period(key),)

    if len(chosen) == 1:
        pack = fetch_line(
            args.code,
            period=chosen[0],
            adjust=args.adjust,
            limit=args.limit,
            beg=args.beg,
            end=args.end,
        )
        print(
            f"{pack.get('symbol')} {pack.get('code')} {pack.get('name') or ''}  "
            f"adjust={pack['adjust']}"
        )
        _print_preview(pack, args.limit if not args.beg else 5)
        return 0

    pack = fetch_lines(
        args.code,
        periods=chosen,
        adjust=args.adjust,
        limit=args.limit,
        beg=args.beg,
        end=args.end,
    )
    print(
        f"{pack.get('symbol')} {pack.get('code')} {pack.get('name') or ''}  "
        f"adjust={pack['adjust']}"
    )
    for period in chosen:
        _print_preview(pack[period], args.limit if not args.beg else 5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
