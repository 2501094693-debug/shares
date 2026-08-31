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
DEFAULT_PERIODS: tuple[str, ...] = BAR_PERIODS

_PERIOD_ALIASES = {
    "1": "1m", "1m": "1m", "1min": "1m", "min1": "1m",
    "5": "5m", "5m": "5m", "5min": "5m",
    "15": "15m", "15m": "15m", "15min": "15m",
    "30": "30m", "30m": "30m", "30min": "30m",
    "60": "60m", "60m": "60m", "60min": "60m", "1h": "60m", "hour": "60m",
    "day": "day", "d": "day", "daily": "day", "101": "day",
    "week": "week", "w": "week", "weekly": "week", "102": "week",
    "month": "month", "m": "month", "monthly": "month", "103": "month",
}
_UNSUPPORTED = {
    **dict.fromkeys(("120", "120m", "2h"), "腾讯不支持 120 分钟 K 线"),
    **dict.fromkeys(("104", "quarter", "q", "season", "qtr"), "腾讯不支持季 K"),
    **dict.fromkeys(("105", "halfyear", "half", "hy", "h", "semiannual"), "腾讯不支持半年 K"),
    **dict.fromkeys(("106", "year", "y", "yearly", "annual"), "腾讯不支持年 K"),
}
_ADJUST = {
    "0": 0, "none": 0, "n": 0,
    "1": 1, "qfq": 1, "forward": 1,
    "2": 2, "hfq": 2, "backward": 2,
}
_ADJUST_LABEL = {0: "none", 1: "qfq", 2: "hfq"}
_FQ_FLAG = {0: "", 1: "qfq", 2: "hfq"}

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


# ---------------------------------------------------------------------------
# 1. 参数计算
# ---------------------------------------------------------------------------

def _period(period: str) -> str:
    key = (period or "day").strip().lower()
    if key in _UNSUPPORTED:
        raise ValueError(_UNSUPPORTED[key])
    if key in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[key]
    if key in PERIOD_TX:
        return key
    raise ValueError("period 须为 1m|5m|15m|30m|60m|day|week|month")


def _adjust(adjust: str | int) -> int:
    key = str(adjust if adjust is not None else "qfq").strip().lower()
    if key not in _ADJUST:
        raise ValueError("adjust 须为 none|qfq|hfq（或 0|1|2）")
    return _ADJUST[key]


def _date(value: str) -> str:
    text = (value or "").replace("-", "").replace("/", "").strip()
    if not text or text in ("0", "1"):
        return text
    if len(text) == 8 and text.isdigit():
        return text
    raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")


def _ymd(value: str) -> str:
    if not value or value in ("0", "1"):
        return ""
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def _params(
    code: str,
    *,
    period: str,
    adjust: str | int,
    limit: int,
    beg: str,
    end: str,
) -> dict[str, Any]:
    """规范化入参，并算出请求 URL / param。"""
    symbol = resolve_symbol(code)
    if not symbol:
        raise ValueError("无效股票代码")

    period = _period(period)\

    fqt = _adjust(adjust)

    cap = int(limit) if limit is not None else 320
    if cap <= 0:
        cap = _MAX_LMT
    cap = max(1, min(cap, _MAX_LMT))

    beg = _date(beg)
    end = _date(end)

    tx = PERIOD_TX[period]
    minute = period in MINUTE_PERIODS
    if minute:
        url, param = _MKLINE_URL, f"{symbol},{tx},,{cap}"
    else:
        url = _FQKLINE_URL
        param = f"{symbol},{tx},{_ymd(beg)},{_ymd(end)},{cap},{_FQ_FLAG.get(fqt, '')}"

    return {
        "symbol": symbol,
        "period": period,
        "tx_period": tx,
        "fqt": fqt,
        "cap": cap,
        "beg": beg,
        "end": end,
        "minute": minute,
        "query": "range" if beg and not minute else "last",
        "adjust": "none" if minute else _ADJUST_LABEL.get(fqt, "none"),
        "url": url,
        "param": param,
    }


# ---------------------------------------------------------------------------
# 2. 请求数据
# ---------------------------------------------------------------------------

def _request(url: str, param: str) -> dict[str, Any]:
    payload = get_json(url, params={"param": param}, headers=_HEADERS, timeout=12) or {}
    return payload if isinstance(payload, dict) else {}


# ---------------------------------------------------------------------------
# 3. 数据解析
# ---------------------------------------------------------------------------

def _parse_row(row: Any, *, minute: bool) -> dict[str, Any] | None:
    if not isinstance(row, (list, tuple)) or len(row) < 5:
        return None
    open_ = to_float(row[1])
    close = to_float(row[2])
    high = to_float(row[3])
    low = to_float(row[4])
    if close is None and open_ is None:
        return None
    raw_time = str(row[0] or "").strip()
    if minute and len(raw_time) >= 12 and raw_time[:12].isdigit():
        time_s = f"{raw_time[0:4]}-{raw_time[4:6]}-{raw_time[6:8]} {raw_time[8:10]}:{raw_time[10:12]}"
    else:
        time_s = raw_time[:19]
    amount = to_float(row[6]) if len(row) > 6 and not isinstance(row[6], dict) else None
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
    """用上一根有效收盘补涨跌额 / 涨跌幅 / 振幅。"""
    prev: float | None = None
    for item in items:
        close = to_float(item.get("close"))
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        if prev not in (None, 0):
            if close is not None:
                item["change"] = round(close - prev, 4)
                item["pct_chg"] = round((close / prev - 1.0) * 100, 4)
            if high is not None and low is not None:
                item["amplitude"] = round((high - low) / prev * 100, 4)
        prev = close if close is not None else prev


def _parse(payload: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """把腾讯 JSON 收成统一 K 线包。

    payload 形如::

        {"data": {"sh600519": {
            "qt": {"sh600519": ["...", "贵州茅台", ...]},
            "qfqday": [[时间, 开, 收, 高, 低, 量, 额], ...],
            "m5":     [[时间, 开, 收, 高, 低, 量, 额], ...],
        }}}

    params 来自 ``_params``，解析时用到：
    symbol / tx_period / minute / fqt / query / beg / end / cap / period / adjust。
    """
    # 1) 定位这只股票的节点。缺字段或类型不对就当空 dict，后面得到空列表而不是崩。
    data = payload.get("data")
    node = data.get(params["symbol"]) if isinstance(data, dict) else None
    node = node if isinstance(node, dict) else {}

    # 2) 从 qt 取名称。腾讯常见是列表，股票名在下标 1；偶发直接给字符串。
    #    依次试 sh600519 / qsh600519 / name，哪个有值用哪个。
    name = ""
    qt = node.get("qt")
    if isinstance(qt, dict):
        for key in (params["symbol"], f"q{params['symbol']}", "name"):
            val = qt.get(key)
            if isinstance(val, list) and len(val) > 1:
                text = str(val[1] or "").strip()
                if text:
                    name = text
                    break
            if isinstance(val, str) and val.strip():
                name = val.strip()
                break

    # 3) 取出 K 线二维数组。
    #    分钟：key 就是腾讯周期名，如 m5。
    #    日/周/月：按复权优先级找。前复权先 qfqday，后复权先 hfqday；
    #    没有对应复权（指数经常只有不复权）再回落到 day / qfqday / hfqday。
    if params["minute"]:
        rows = node.get(params["tx_period"]) or []
    else:
        keys = []
        if params["fqt"] == 1:
            keys.append(f"qfq{params['tx_period']}")
        elif params["fqt"] == 2:
            keys.append(f"hfq{params['tx_period']}")
        keys.extend((params["tx_period"], "day", "qfqday", "hfqday"))
        rows = next((node[k] for k in keys if isinstance(node.get(k), list) and node[k]), [])

    # 4) 每一行 [时间, 开, 收, 高, 低, 量, 额] → 一根 K 线字典；坏行丢掉。
    items: list[dict[str, Any]] = []
    if isinstance(rows, list):
        for row in rows:
            parsed = _parse_row(row, minute=params["minute"])
            if parsed:
                items.append(parsed)

    # 5) 裁剪。range=按日期过滤（仅日/周/月且传了 beg）；last=只留最近 cap 根。
    if params["query"] == "range":
        lo, hi = _ymd(params["beg"]), _ymd(params["end"])
        items = [
            it
            for it in items
            if (not lo or str(it.get("time") or "")[:10] >= lo)
            and (not hi or str(it.get("time") or "")[:10] <= hi)
        ]
    elif len(items) > params["cap"]:
        items = items[-params["cap"] :]

    # 6) 腾讯这套接口不带涨跌，用上一根有效收盘补 change / pct_chg / amplitude。
    _fill_change(items)

    # source 为空表示没拉到 K 线，上层 fetcher 会改走东财。
    return {
        "code": re.sub(r"[^0-9]", "", params["symbol"]) or params["symbol"],
        "symbol": params["symbol"],
        "name": name,
        "period": params["period"],
        "tx_period": params["tx_period"],
        "adjust": params["adjust"],
        "query": params["query"],
        "source": "tencent" if items else "",
        "count": len(items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

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
    params = _params(code, period=period, adjust=adjust, limit=limit, beg=beg, end=end)
    try:
        payload = _request(params["url"], params["param"])
    except Exception:
        logger.exception("tencent line failed %s %s", params["symbol"], params["period"])
        raise
    return _parse(payload, params)


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

    canon = [_period(period) for period in (periods or DEFAULT_PERIODS)]
    result: dict[str, Any] = {
        "code": "",
        "symbol": symbol,
        "name": "",
        "adjust": _ADJUST_LABEL.get(_adjust(adjust), "none"),
        "source": "tencent",
    }
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(canon)))) as pool:
        futs = {
            period: pool.submit(
                fetch_line, code, period=period, adjust=adjust, limit=limit, beg=beg, end=end
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
    parser.add_argument("code", nargs="?", default="600519", help="600519 / sh000001 / SZ000001")
    parser.add_argument("--period", default="bars", help="周期，或 bars(日周月) / minutes")
    parser.add_argument("--adjust", default="qfq", help="none|qfq|hfq")
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
        chosen = (_period(key),)
    preview = args.limit if not args.beg else 5

    if len(chosen) == 1:
        pack = fetch_line(
            args.code, period=chosen[0], adjust=args.adjust,
            limit=args.limit, beg=args.beg, end=args.end,
        )
        print(f"{pack.get('symbol')} {pack.get('code')} {pack.get('name') or ''}  adjust={pack['adjust']}")
        _print_preview(pack, preview)
        return 0

    pack = fetch_lines(
        args.code, periods=chosen, adjust=args.adjust,
        limit=args.limit, beg=args.beg, end=args.end,
    )
    print(f"{pack.get('symbol')} {pack.get('code')} {pack.get('name') or ''}  adjust={pack['adjust']}")
    for period in chosen:
        _print_preview(pack[period], preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
