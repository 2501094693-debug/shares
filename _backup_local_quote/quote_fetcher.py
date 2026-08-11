"""东方财富个股盘口 / 估值 / 区间涨幅。

供公司详情页补全指标；失败时返回空 dict，由上层保留乐咕字段兜底。
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from message.disclosure.http_util import detect_market, http_get, normalize_code

logger = logging.getLogger(__name__)

QUOTE_TTL = 60  # 秒
_cache_lock = threading.Lock()
_mem_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _http_get_json(url: str, *, params: dict[str, Any], headers: dict[str, str], timeout: int = 12) -> Any:
    """优先走项目 http_get；失败时回退 requests 并重试一次。"""
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = http_get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(0.25 * (attempt + 1))
    try:
        import requests

        resp = requests.get(url, params=params, headers={**headers, "User-Agent": "Mozilla/5.0"}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        raise last_exc or exc

# push2 字段：与东财行情页 / akshare stock_bid_ask_em 对齐
_PUSH2_FIELDS = (
    "f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f55,f57,f58,f60,f62,f71,"
    "f84,f85,f92,f116,f117,f127,f161,f162,f163,f164,f167,f168,f169,f170,"
    "f171,f173,f174,f175,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,"
    "f198,f199,f292,f301,"
    "f11,f12,f13,f14,f15,f16,f17,f18,f19,f20,"
    "f31,f32,f33,f34,f35,f36,f37,f38,f39,f40"
)


def _secid(code: str) -> str:
    c = normalize_code(code)
    market = detect_market(c)
    # 沪市 1.xxx；深市 / 北交所 0.xxx
    return f"1.{c}" if market == "sse" else f"0.{c}"


def _num(v: Any) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
    # 东财偶发用极大负数表示无效
    if n <= -1e10:
        return None
    return n


def _fmt_price(v: Any, digits: int = 2) -> str:
    n = _num(v)
    if n is None:
        return ""
    return f"{n:.{digits}f}"


def _fmt_pct(v: Any, digits: int = 2) -> str:
    n = _num(v)
    if n is None:
        return ""
    return f"{n:.{digits}f}%"


def _fmt_signed(v: Any, digits: int = 2) -> str:
    n = _num(v)
    if n is None:
        return ""
    return f"{n:.{digits}f}"


def _fmt_yi_wan(v: Any, *, unit_yi: bool = False) -> str:
    """金额/市值：元 → 亿 / 万。"""
    n = _num(v)
    if n is None:
        return ""
    abs_n = abs(n)
    sign = "-" if n < 0 else ""
    if unit_yi or abs_n >= 1e8:
        return f"{sign}{abs_n / 1e8:.2f}亿".replace(".00亿", "亿")
    if abs_n >= 1e4:
        val = abs_n / 1e4
        text = f"{val:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}万"
    return f"{sign}{abs_n:.0f}"


def _fmt_shares(v: Any) -> str:
    """股数 → 亿 / 万。"""
    n = _num(v)
    if n is None:
        return ""
    abs_n = abs(n)
    if abs_n >= 1e8:
        text = f"{abs_n / 1e8:.2f}".rstrip("0").rstrip(".")
        return f"{text}亿"
    if abs_n >= 1e4:
        text = f"{abs_n / 1e4:.2f}".rstrip("0").rstrip(".")
        return f"{text}万"
    return f"{abs_n:.0f}"


def _fmt_volume_hands(v: Any) -> str:
    """成交量（手）→ 万。"""
    n = _num(v)
    if n is None:
        return ""
    abs_n = abs(n)
    if abs_n >= 1e4:
        return f"{abs_n / 1e4:.1f}万".replace(".0万", "万")
    return f"{abs_n:.0f}"


def _fmt_list_date(v: Any) -> str:
    s = str(v or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _sum_side(data: dict[str, Any], vol_keys: tuple[str, ...]) -> float | None:
    total = 0.0
    ok = False
    for k in vol_keys:
        n = _num(data.get(k))
        if n is None:
            continue
        total += n
        ok = True
    return total if ok else None


def _fetch_push2(code: str) -> dict[str, Any]:
    secid = _secid(code)
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": _PUSH2_FIELDS,
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    headers = {"Referer": "https://quote.eastmoney.com/"}
    payload = _http_get_json(url, params=params, headers=headers, timeout=12) or {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _fetch_fund_flow(code: str) -> dict[str, Any]:
    """主力净流入（今日 + 近5日合计）。"""
    market = detect_market(normalize_code(code))
    market_map = {"sse": 1, "szse": 0, "bse": 0}
    mid = market_map.get(market, 1 if normalize_code(code).startswith("6") else 0)
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "lmt": "0",
        "klt": "101",
        "secid": f"{mid}.{normalize_code(code)}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
        "_": int(time.time() * 1000),
    }
    headers = {"Referer": "https://data.eastmoney.com/zjlx/"}
    payload = _http_get_json(url, params=params, headers=headers, timeout=12) or {}
    klines = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get(
        "klines"
    ) or []
    if not klines:
        return {}
    rows = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 2:
            continue
        main = _num(parts[1])
        if main is None:
            continue
        rows.append(main)
    if not rows:
        return {}
    today = rows[-1]
    last5 = sum(rows[-5:]) if len(rows) >= 1 else today
    return {
        "main_net_inflow": _fmt_yi_wan(today),
        "main_net_inflow_5d": _fmt_yi_wan(last5),
    }


def _pct_change(cur: float, base: float) -> str:
    if base == 0:
        return ""
    return _fmt_pct((cur / base - 1.0) * 100)


def _fetch_period_returns(code: str) -> dict[str, Any]:
    """用日 K 推算区间涨幅与高低点。"""
    market = detect_market(normalize_code(code))
    mid = 1 if market == "sse" else 0
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": f"{mid}.{normalize_code(code)}",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "0",
        "beg": "19900101",
        "end": "20500101",
        "lmt": "10000",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    headers = {"Referer": "https://quote.eastmoney.com/"}
    payload = _http_get_json(url, params=params, headers=headers, timeout=12) or {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    klines = data.get("klines") or []
    if len(klines) < 2:
        return {}

    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    dates: list[str] = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 5:
            continue
        d, o, h, low, c = parts[0], _num(parts[1]), _num(parts[2]), _num(parts[3]), _num(parts[4])
        if c is None:
            continue
        dates.append(str(d)[:10])
        closes.append(c)
        if h is not None:
            highs.append(h)
        if low is not None:
            lows.append(low)

    if len(closes) < 2:
        return {}

    last = closes[-1]
    out: dict[str, Any] = {}

    def at(n: int) -> float | None:
        if len(closes) > n:
            return closes[-(n + 1)]
        return None

    mapping = {
        "change_3d": 3,
        "change_5d": 5,
        "change_10d": 10,
        "change_20d": 20,
        "change_60d": 60,
        "change_half_year": 120,
        "change_1y": 250,
    }
    for key, days in mapping.items():
        base = at(days)
        if base is not None:
            out[key] = _pct_change(last, base)

    # 今年以来：找当年首个交易日
    year = dates[-1][:4] if dates else ""
    if year:
        ytd_base = None
        for d, c in zip(dates, closes):
            if d.startswith(year):
                ytd_base = c
                break
        if ytd_base is not None:
            out["change_ytd"] = _pct_change(last, ytd_base)

    # 近1日用最后两根更贴近收盘口径；盘中仍以 push2 涨幅为准
    if len(closes) >= 2:
        out["change_1d_close"] = _pct_change(last, closes[-2])

    window = min(252, len(highs), len(lows))
    if window >= 5:
        out["high_52w"] = _fmt_price(max(highs[-window:]))
        out["low_52w"] = _fmt_price(min(lows[-window:]))

    if highs and lows:
        out["high_all"] = _fmt_price(max(highs))
        out["low_all"] = _fmt_price(min(lows))

    return out


def _map_push2(data: dict[str, Any]) -> dict[str, Any]:
    price = _num(data.get("f43"))
    open_p = _num(data.get("f46"))
    prev = _num(data.get("f60"))
    high = _num(data.get("f44"))
    low = _num(data.get("f45"))

    solid = ""
    if price is not None and open_p is not None and prev not in (None, 0):
        solid = _fmt_pct((price - open_p) / prev * 100)
    elif price is not None and open_p is not None and open_p != 0:
        solid = _fmt_pct((price - open_p) / open_p * 100)

    bid_vol = _sum_side(data, ("f20", "f18", "f16", "f14", "f12"))
    ask_vol = _sum_side(data, ("f32", "f34", "f36", "f38", "f40"))
    # 东财部分字段单位是「手」的手数计数；五档量常见需 *100 才是股。
    # 截图委买/委卖为较小整数（手），优先用 f191/f192；否则用五档合计（已是手口径时不乘）。
    bid_ask_ratio = _fmt_pct(data.get("f191"))
    bid_ask_diff = _fmt_signed(data.get("f192"), 0)

    out: dict[str, Any] = {
        # 覆盖列表/乐咕同名字段
        "price": _fmt_price(price),
        "change_1d": _fmt_pct(data.get("f170")),
        "pe": _fmt_signed(data.get("f162")),
        "pe_ttm": _fmt_signed(data.get("f164")),
        "pb": _fmt_signed(data.get("f167")),
        "roe": _fmt_pct(data.get("f173")),
        # 当日行情
        "avg_price": _fmt_price(data.get("f71")),
        "change_amt": _fmt_signed(data.get("f169")),
        "open": _fmt_price(open_p),
        "prev_close": _fmt_price(prev),
        "high": _fmt_price(high),
        "low": _fmt_price(low),
        "volume": _fmt_volume_hands(data.get("f47")),
        "amount": _fmt_yi_wan(data.get("f48")),
        "turnover": _fmt_pct(data.get("f168")),
        "volume_ratio": _fmt_signed(data.get("f50")),
        "amplitude": _fmt_pct(data.get("f171")),
        "solid_change": solid,
        "limit_up": _fmt_price(data.get("f51")),
        "limit_down": _fmt_price(data.get("f52")),
        "outer_vol": _fmt_volume_hands(data.get("f49")),
        "inner_vol": _fmt_volume_hands(data.get("f161")),
        "bid_vol": _fmt_signed(bid_vol, 0) if bid_vol is not None else "",
        "ask_vol": _fmt_signed(ask_vol, 0) if ask_vol is not None else "",
        "bid_ask_diff": bid_ask_diff,
        "bid_ask_ratio": bid_ask_ratio,
        # 估值
        "pe_static": _fmt_signed(data.get("f163")),
        "eps": _fmt_signed(data.get("f55"), 3),
        "bvps": _fmt_signed(data.get("f92")),
        "ps_ttm": "",
        # 股本
        "total_shares": _fmt_shares(data.get("f84")),
        "float_shares": _fmt_shares(data.get("f85")),
        "float_market_cap": _fmt_yi_wan(data.get("f117"), unit_yi=True),
        "total_market_cap": _fmt_yi_wan(data.get("f116"), unit_yi=True),
        "list_date": _fmt_list_date(data.get("f189")),
        "industry_name_em": str(data.get("f127") or "").strip(),
    }

    # 营收/净利同比等（若有）
    if _num(data.get("f184")) is not None:
        out["revenue_yoy"] = _fmt_pct(data.get("f184"))
    if _num(data.get("f186")) is not None:
        out["profit_yoy"] = _fmt_pct(data.get("f186"))

    # market_cap 保持与乐咕一致：亿元数值（无单位后缀）
    mcap_yi = _num(data.get("f116"))
    if mcap_yi is not None:
        out["market_cap"] = f"{mcap_yi / 1e8:.2f}".rstrip("0").rstrip(".")

    # 清理空串
    return {k: v for k, v in out.items() if v not in (None, "")}


def fetch_stock_quote(code: str, *, force: bool = False) -> dict[str, Any]:
    """拉取并规范化个股盘口指标。"""
    code = normalize_code(code)
    if not code:
        return {}

    now = time.time()
    with _cache_lock:
        hit = _mem_cache.get(code)
        if not force and hit and now - hit[0] < QUOTE_TTL:
            return dict(hit[1])

    result: dict[str, Any] = {}
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_quote = pool.submit(_fetch_push2, code)
            fut_flow = pool.submit(_fetch_fund_flow, code)
            fut_ret = pool.submit(_fetch_period_returns, code)

            try:
                raw = fut_quote.result()
                if raw:
                    result.update(_map_push2(raw))
            except Exception as exc:  # noqa: BLE001
                logger.warning("push2 quote failed %s: %s", code, exc)

            try:
                result.update(fut_flow.result() or {})
            except Exception as exc:  # noqa: BLE001
                logger.warning("fund flow failed %s: %s", code, exc)

            try:
                periods = fut_ret.result() or {}
                # 近1日优先盘中 push2；区间涨幅用 K 线
                periods.pop("change_1d_close", None)
                # change_5d / change_ytd：有 K 线则覆盖乐咕，更贴近东财盘口
                result.update(periods)
            except Exception as exc:  # noqa: BLE001
                logger.warning("period returns failed %s: %s", code, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("quote fetch failed %s: %s", code, exc)
        return {}

    if result:
        with _cache_lock:
            _mem_cache[code] = (now, dict(result))
    return result
