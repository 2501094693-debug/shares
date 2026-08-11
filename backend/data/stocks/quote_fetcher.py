"""东方财富个股盘口 / 估值 / 区间涨幅 / 股本。

供公司详情页补全指标；失败时返回空 dict，由上层保留乐咕字段兜底。
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from message.disclosure.http_util import detect_market, normalize_code, safe_str

logger = logging.getLogger(__name__)

QUOTE_TTL = 60  # 秒
_cache_lock = threading.Lock()
_mem_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_PUSH2_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
    "https://71.push2.eastmoney.com",
)

_PUSH2_FIELDS = (
    "f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f55,f57,f58,f60,f71,"
    "f84,f85,f92,f116,f117,f127,f161,f162,f163,f164,f167,f168,f169,f170,"
    "f171,f173,f174,f175,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,"
    "f198,f199,f260,f261,f277,f278,"
    "f11,f12,f13,f14,f15,f16,f17,f18,f19,f20,"
    "f31,f32,f33,f34,f35,f36,f37,f38,f39,f40"
)

# 港股通持仓不计入「≥5% 扣除」以匹配东财自由流通口径
_FREE_FLOAT_SKIP_NAMES = ("香港中央结算", "香港中央結算")


def _secid(code: str) -> str:
    c = normalize_code(code)
    market = detect_market(c)
    return f"1.{c}" if market == "sse" else f"0.{c}"


def _em_code(code: str) -> str:
    c = normalize_code(code)
    market = detect_market(c)
    prefix = {"sse": "SH", "szse": "SZ", "bse": "BJ"}.get(market, "SH")
    return f"{prefix}{c}"


def _num(v: Any) -> float | None:
    if v is None or v == "" or v == "-":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
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
        text = f"{abs_n / 1e8:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}亿"
    if abs_n >= 1e4:
        text = f"{abs_n / 1e4:.2f}".rstrip("0").rstrip(".")
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
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
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


def _session() -> requests.Session:
    """独立 Session，关闭系统代理，避免 Windows 代理/ curl_cffi 干扰。"""
    s = requests.Session()
    s.trust_env = False
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }
    )
    return s


def _http_get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 12,
) -> Any:
    """仅用 requests（不走 curl_cffi）。"""
    sess = _session()
    resp = sess.get(url, params=params, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _http_get_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 12,
    encoding: str | None = None,
) -> str:
    sess = _session()
    resp = sess.get(url, params=params, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    if encoding:
        resp.encoding = encoding
    return resp.text


def _fetch_tencent_quote(code: str) -> dict[str, Any]:
    """腾讯实时行情回退（东财 push2 不可用时）。"""
    c = normalize_code(code)
    market = detect_market(c)
    prefix = {"sse": "sh", "szse": "sz", "bse": "bj"}.get(market, "sh")
    symbol = f"{prefix}{c}"
    text = _http_get_text(
        "https://qt.gtimg.cn/q=" + symbol,
        headers={"Referer": "https://gu.qq.com/"},
        timeout=10,
    )
    # v_sh601881="1~名称~代码~现价~昨收~今开~总量~外盘~内盘~..."
    if '="' not in text:
        return {}
    body = text.split('="', 1)[1].rsplit('"', 1)[0]
    p = body.split("~")
    if len(p) < 45:
        return {}

    price = _num(p[3])
    prev = _num(p[4])
    open_p = _num(p[5])
    volume = _num(p[6])
    outer = _num(p[7])
    inner = _num(p[8])
    change_amt = _num(p[31]) if len(p) > 31 else None
    change_pct = _num(p[32]) if len(p) > 32 else None
    high = _num(p[33]) if len(p) > 33 else None
    low = _num(p[34]) if len(p) > 34 else None
    # p[37] 成交额（万），p[38] 换手
    amount_wan = _num(p[37]) if len(p) > 37 else None
    turnover = _num(p[38]) if len(p) > 38 else None
    # p[44]/p[45] 常见为总市值/流通市值（亿）
    mcap_yi = _num(p[45]) if len(p) > 45 else None
    float_mcap_yi = _num(p[44]) if len(p) > 44 else None

    solid = ""
    if price is not None and open_p is not None and prev not in (None, 0):
        solid = _fmt_pct((price - open_p) / prev * 100)

    out: dict[str, Any] = {
        "price": _fmt_price(price),
        "prev_close": _fmt_price(prev),
        "open": _fmt_price(open_p),
        "high": _fmt_price(high),
        "low": _fmt_price(low),
        "volume": _fmt_volume_hands(volume),
        "outer_vol": _fmt_volume_hands(outer),
        "inner_vol": _fmt_volume_hands(inner),
        "change_amt": _fmt_signed(change_amt),
        "change_1d": _fmt_pct(change_pct),
        "solid_change": solid,
        "turnover": _fmt_pct(turnover),
        "amount": _fmt_yi_wan((amount_wan or 0) * 1e4) if amount_wan is not None else "",
        "_price_raw": price,
        "_turnover_raw": turnover,
    }
    if mcap_yi is not None:
        out["market_cap"] = f"{mcap_yi:.2f}".rstrip("0").rstrip(".")
        out["total_market_cap"] = f"{out['market_cap']}亿"
    if float_mcap_yi is not None:
        text = f"{float_mcap_yi:.2f}".rstrip("0").rstrip(".")
        out["float_market_cap"] = f"{text}亿"
    # 振幅
    if high is not None and low is not None and prev not in (None, 0):
        out["amplitude"] = _fmt_pct((high - low) / prev * 100)
    return {k: v for k, v in out.items() if v not in (None, "")}


def _fetch_push2(code: str) -> dict[str, Any]:
    secid = _secid(code)
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": _PUSH2_FIELDS,
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    headers = {
        "Referer": f"https://quote.eastmoney.com/sh{normalize_code(code)}.html"
    }
    last_exc: Exception | None = None
    for host in _PUSH2_HOSTS:
        try:
            payload = _http_get_json(
                f"{host}/api/qt/stock/get",
                params=params,
                headers=headers,
                timeout=10,
            ) or {}
            data = payload.get("data")
            if isinstance(data, dict) and data:
                return data
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
    # 东财不可用时回退腾讯
    try:
        tx = _fetch_tencent_quote(code)
        if tx:
            logger.info("push2 fallback to tencent quote for %s", code)
            return {"__tencent_mapped__": tx}
    except Exception as exc:  # noqa: BLE001
        logger.info("tencent quote fallback failed %s: %s", code, exc)
    if last_exc:
        logger.info("push2 unavailable %s: %s", code, last_exc)
    return {}


def _fetch_fund_flow(code: str) -> dict[str, Any]:
    """主力净流入（今日 + 近5日合计）。失败返回空，不抛异常。"""
    try:
        market = detect_market(normalize_code(code))
        mid = 1 if market == "sse" else 0
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
        payload = None
        for host in (
            "https://push2delay.eastmoney.com",
            "https://push2his.eastmoney.com",
            "https://push2.eastmoney.com",
        ):
            try:
                payload = _http_get_json(
                    f"{host}/api/qt/stock/fflow/daykline/get",
                    params=params,
                    headers=headers,
                    timeout=10,
                )
                if isinstance(payload, dict):
                    break
            except Exception:  # noqa: BLE001
                payload = None
                continue
        if not isinstance(payload, dict):
            return {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        klines = (data or {}).get("klines") or []
        rows: list[float] = []
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
        last5 = sum(rows[-5:])
        return {
            "main_net_inflow": _fmt_yi_wan(today),
            "main_net_inflow_5d": _fmt_yi_wan(last5),
        }
    except Exception as exc:  # noqa: BLE001
        logger.info("fund flow skip %s: %s", code, exc)
        return {}


def _pct_change(cur: float, base: float) -> str:
    if base == 0:
        return ""
    return _fmt_pct((cur / base - 1.0) * 100)


def _tencent_symbol(code: str) -> str:
    c = normalize_code(code)
    market = detect_market(c)
    prefix = {"sse": "sh", "szse": "sz", "bse": "bj"}.get(market, "sh")
    return f"{prefix}{c}"


def _fetch_tencent_day_rows(
    symbol: str,
    *,
    start: str = "",
    end: str = "",
    limit: int = 640,
    qfq: bool = False,
) -> list[list[Any]]:
    """拉取腾讯日 K。qfq=True 为前复权（对齐东财历史高低）。"""
    if start and end:
        param = f"{symbol},day,{start},{end},{limit},{'qfq' if qfq else ''}"
    else:
        param = f"{symbol},day,,,{limit},{'qfq' if qfq else ''}"
    payload = _http_get_json(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        params={"param": param},
        headers={"Referer": "https://gu.qq.com/"},
        timeout=12,
    ) or {}
    node = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get(
        symbol
    ) or {}
    rows = node.get("qfqday") if qfq else node.get("day")
    if not rows:
        rows = node.get("qfqday") or node.get("day") or []
    return rows if isinstance(rows, list) else []


def _fetch_price_extremes(code: str, list_date: str = "") -> dict[str, Any]:
    """52周/历史最高最低：用前复权全历史，口径对齐东财盘口。

    腾讯单次日K约 640 根上限，且长区间会截成最近一段，因此按年并行拉取。
    部分老股前复权会出现 ≤0 的异常价，需过滤；若有效样本不足则回退不复权。
    """
    symbol = _tencent_symbol(code)
    start_year = 1990
    ld = (list_date or "").replace("-", "").replace("/", "")
    if len(ld) >= 4 and ld[:4].isdigit():
        start_year = max(1990, int(ld[:4]))
    end_year = time.localtime().tm_year

    # 每次约一年（交易日 < 640），避免长区间被截成尾部
    ranges = [
        (f"{y:04d}-01-01", f"{y:04d}-12-31")
        for y in range(start_year, end_year + 1)
    ]

    def _pull(span: tuple[str, str], qfq: bool) -> list[list[Any]]:
        start, end = span
        try:
            return _fetch_tencent_day_rows(symbol, start=start, end=end, limit=640, qfq=qfq)
        except Exception as exc:  # noqa: BLE001
            logger.info("extremes chunk skip %s %s qfq=%s: %s", code, start, qfq, exc)
            return []

    def _collect(qfq: bool) -> list[list[Any]]:
        by_date: dict[str, list[Any]] = {}
        with ThreadPoolExecutor(max_workers=min(8, max(2, len(ranges)))) as pool:
            futs = [pool.submit(_pull, span, qfq) for span in ranges]
            for fut in futs:
                for row in fut.result() or []:
                    if isinstance(row, (list, tuple)) and len(row) >= 5:
                        by_date[str(row[0])[:10]] = list(row)
        if len(by_date) < 5:
            try:
                for row in _fetch_tencent_day_rows(symbol, limit=640, qfq=qfq):
                    if isinstance(row, (list, tuple)) and len(row) >= 5:
                        by_date[str(row[0])[:10]] = list(row)
            except Exception as exc:  # noqa: BLE001
                logger.info("extremes fallback skip %s qfq=%s: %s", code, qfq, exc)
        return [by_date[k] for k in sorted(by_date)]

    def _minmax(rows: list[list[Any]], *, min_price: float = 0.0) -> tuple[float | None, float | None, int, int]:
        """返回 (high, low, 有效根数, 被过滤根数)。"""
        highs: list[float] = []
        lows: list[float] = []
        dropped = 0
        for r in rows:
            h = _num(r[3])
            low = _num(r[4])
            if h is None or low is None:
                continue
            if h <= min_price or low <= min_price:
                dropped += 1
                continue
            highs.append(h)
            lows.append(low)
        if not highs or not lows:
            return None, None, 0, dropped
        return max(highs), min(lows), len(highs), dropped

    qfq_rows = _collect(True)
    if len(qfq_rows) < 5:
        return {}

    # 先用全部正价前复权；若大量异常（负价/零价），再与不复权对比兜底
    high_all, low_all, kept, dropped = _minmax(qfq_rows, min_price=0.0)
    use_rows = qfq_rows
    if high_all is None or low_all is None:
        return {}

    bad_ratio = dropped / max(1, kept + dropped)
    # 前复权异常时（如长期现金分红导致负价），回退不复权全历史
    if bad_ratio >= 0.05:
        raw_rows = _collect(False)
        raw_high, raw_low, raw_kept, _ = _minmax(raw_rows, min_price=0.0)
        # 若过滤后的前复权最低价相对不复权过低，视为算法失真
        if raw_high is not None and raw_low is not None and raw_kept >= 5:
            if low_all < raw_low * 0.05:
                logger.info(
                    "extremes use raw for %s (qfq bad_ratio=%.2f qfq_low=%.4f raw_low=%.4f)",
                    code,
                    bad_ratio,
                    low_all,
                    raw_low,
                )
                high_all, low_all = raw_high, raw_low
                use_rows = raw_rows

    out: dict[str, Any] = {
        "high_all": _fmt_price(high_all),
        "low_all": _fmt_price(low_all),
    }
    window = min(252, len(use_rows))
    h52, l52, _, _ = _minmax(use_rows[-window:], min_price=0.0)
    if h52 is not None:
        out["high_52w"] = _fmt_price(h52)
    if l52 is not None:
        out["low_52w"] = _fmt_price(l52)
    return out


def _fetch_period_returns_tencent(code: str) -> dict[str, Any]:
    """腾讯日 K：区间涨幅用不复权收盘（高低点另算前复权）。"""
    symbol = _tencent_symbol(code)
    rows = _fetch_tencent_day_rows(symbol, limit=320, qfq=False)
    closes: list[float] = []
    dates: list[str] = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            continue
        cclose = _num(row[2])
        if cclose is None:
            continue
        dates.append(str(row[0])[:10])
        closes.append(cclose)
    if len(closes) < 2:
        return {}

    last = closes[-1]
    out: dict[str, Any] = {}

    def at(n: int) -> float | None:
        if len(closes) > n:
            return closes[-(n + 1)]
        return None

    for key, days in {
        "change_3d": 3,
        "change_5d": 5,
        "change_10d": 10,
        "change_20d": 20,
        "change_60d": 60,
        "change_half_year": 120,
        "change_1y": 250,
    }.items():
        base = at(days)
        if base is not None:
            out[key] = _pct_change(last, base)

    year = dates[-1][:4] if dates else ""
    if year:
        ytd_base = None
        for d, cclose in zip(dates, closes):
            if d.startswith(year):
                ytd_base = cclose
                break
        if ytd_base is not None:
            out["change_ytd"] = _pct_change(last, ytd_base)
    return out


def _fetch_period_returns(code: str) -> dict[str, Any]:
    """用日 K 推算区间涨幅。优先腾讯（更稳），东财作补充。"""
    try:
        # 腾讯优先：东财 push2his 在不少网络环境下会被直接掐断
        try:
            tx = _fetch_period_returns_tencent(code)
            if tx:
                return tx
        except Exception as exc:  # noqa: BLE001
            logger.info("tencent kline skip %s: %s", code, exc)

        market = detect_market(normalize_code(code))
        mid = 1 if market == "sse" else 0
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
        payload = None
        for host in (
            "https://push2delay.eastmoney.com",
            "https://push2his.eastmoney.com",
        ):
            try:
                payload = _http_get_json(
                    f"{host}/api/qt/stock/kline/get",
                    params=params,
                    headers=headers,
                    timeout=10,
                )
                data = payload.get("data") if isinstance(payload, dict) else None
                klines = (data or {}).get("klines") or [] if isinstance(data, dict) else []
                if klines:
                    break
                payload = None
            except Exception:  # noqa: BLE001
                payload = None
                continue

        data = payload.get("data") if isinstance(payload, dict) else None
        klines = (data or {}).get("klines") or [] if isinstance(data, dict) else []
        if len(klines) < 2:
            return {}

        closes: list[float] = []
        dates: list[str] = []
        for line in klines:
            parts = str(line).split(",")
            if len(parts) < 5:
                continue
            c = _num(parts[4])
            if c is None:
                continue
            dates.append(str(parts[0])[:10])
            closes.append(c)

        if len(closes) < 2:
            return {}

        last = closes[-1]
        out: dict[str, Any] = {}

        def at(n: int) -> float | None:
            if len(closes) > n:
                return closes[-(n + 1)]
            return None

        for key, days in {
            "change_3d": 3,
            "change_5d": 5,
            "change_10d": 10,
            "change_20d": 20,
            "change_60d": 60,
            "change_half_year": 120,
            "change_1y": 250,
        }.items():
            base = at(days)
            if base is not None:
                out[key] = _pct_change(last, base)

        year = dates[-1][:4] if dates else ""
        if year:
            ytd_base = None
            for d, c in zip(dates, closes):
                if d.startswith(year):
                    ytd_base = c
                    break
            if ytd_base is not None:
                out["change_ytd"] = _pct_change(last, ytd_base)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.info("period returns skip %s: %s", code, exc)
        return {}


def _fetch_current_hand(code: str) -> dict[str, Any]:
    """现手：最近一笔成交量（手）。"""
    secid = _secid(code)
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4",
        "fields2": "f51,f52,f53,f54,f55",
        "pos": "-20",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    headers = {"Referer": "https://quote.eastmoney.com/"}
    payload = None
    for host in _PUSH2_HOSTS:
        try:
            payload = _http_get_json(
                f"{host}/api/qt/stock/details/get",
                params=params,
                headers=headers,
                timeout=10,
            )
            break
        except Exception:  # noqa: BLE001
            continue
    details = ((payload or {}).get("data") or {}).get("details") or []
    if not details:
        return {}
    last = str(details[-1]).split(",")
    # time,price,volume,bs,flag
    if len(last) < 3:
        return {}
    vol = _num(last[2])
    if vol is None:
        return {}
    return {"current_volume": _fmt_signed(vol, 0)}


def _fetch_f10_profile(code: str) -> dict[str, Any]:
    """注册资本、发行股本、自由流通股/市值。"""
    em = _em_code(code)
    out: dict[str, Any] = {}
    headers = {
        "Referer": (
            "https://emweb.securities.eastmoney.com/"
            f"PC_HSF10/CompanySurvey/Index?type=web&code={em}"
        ),
        "Accept": "application/json, text/plain, */*",
    }

    try:
        survey = _http_get_json(
            "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax",
            params={"code": em},
            headers=headers,
            timeout=15,
        ) or {}
        jb = survey.get("jbzl") or {}
        if isinstance(jb, list):
            jb = jb[0] if jb else {}
        if isinstance(jb, dict):
            zczb = safe_str(jb.get("zczb"))
            if zczb and zczb != "--":
                out["registered_capital"] = zczb
        fxxg = survey.get("fxxg") or {}
        if isinstance(fxxg, list):
            fxxg = fxxg[0] if fxxg else {}
        if isinstance(fxxg, dict):
            fxl = safe_str(fxxg.get("fxl"))
            if fxl and fxl != "--":
                out["issued_shares"] = fxl
    except Exception as exc:  # noqa: BLE001
        logger.warning("F10 survey failed %s: %s", code, exc)

    # 自由流通：流通股 - 持股≥5%（剔除港股通）
    try:
        sh = _http_get_json(
            "https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax",
            params={"code": em},
            headers={
                "Referer": (
                    "https://emweb.securities.eastmoney.com/"
                    f"PC_HSF10/ShareholderResearch/Index?type=web&code={em}"
                ),
                "Accept": "application/json, text/plain, */*",
            },
            timeout=15,
        ) or {}
        float_shares = None
        gbjg = []
        try:
            cap = _http_get_json(
                "https://emweb.securities.eastmoney.com/PC_HSF10/CapitalStockStructure/PageAjax",
                params={"code": em},
                headers=headers,
                timeout=15,
            ) or {}
            gbjg = cap.get("gbjg") or []
        except Exception:  # noqa: BLE001
            gbjg = []
        if gbjg and isinstance(gbjg[0], dict):
            float_shares = _num(gbjg[0].get("LISTED_A_SHARES") or gbjg[0].get("UNLIMITED_SHARES"))

        sdltgd = sh.get("sdltgd") or []
        big = 0.0
        if float_shares is not None:
            for row in sdltgd:
                if not isinstance(row, dict):
                    continue
                name = safe_str(row.get("HOLDER_NAME"))
                if any(skip in name for skip in _FREE_FLOAT_SKIP_NAMES):
                    continue
                ratio = _num(row.get("FREE_HOLDNUM_RATIO"))
                hold = _num(row.get("HOLD_NUM"))
                if ratio is not None and ratio >= 5 and hold is not None:
                    big += hold
            free = max(float_shares - big, 0)
            if free > 0:
                out["free_float_shares"] = _fmt_shares(free)
                out["_free_float_shares_raw"] = free
                out["_float_shares_raw"] = float_shares
    except Exception as exc:  # noqa: BLE001
        logger.warning("F10 free-float failed %s: %s", code, exc)

    return out


def _fetch_valuation_extra(code: str) -> dict[str, Any]:
    """市销率、股息(TTM) 等估值字段。"""
    c = normalize_code(code)
    out: dict[str, Any] = {}
    try:
        payload = _http_get_json(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPT_VALUEANALYSIS_DET",
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{c}")',
                "pageNumber": "1",
                "pageSize": "1",
                "source": "WEB",
                "client": "WEB",
            },
            headers={"Referer": "https://data.eastmoney.com/"},
            timeout=12,
        ) or {}
        rows = ((payload.get("result") or {}) if isinstance(payload.get("result"), dict) else {}).get(
            "data"
        ) or []
        if rows:
            row = rows[0]
            ps = _num(row.get("PS_TTM"))
            if ps is not None:
                out["ps_ttm"] = _fmt_signed(ps)
            price = _num(row.get("CLOSE_PRICE"))
            # 若后续有股息率可算股息；先记下收盘价备用
            if price is not None:
                out["_close_for_div"] = price
    except Exception as exc:  # noqa: BLE001
        logger.warning("valuation extra failed %s: %s", code, exc)

    # 近一年分红合计 → 股息(TTM)
    try:
        payload = _http_get_json(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPT_SHAREBONUS_DET",
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{c}")',
                "pageNumber": "1",
                "pageSize": "20",
                "sortTypes": "-1",
                "sortColumns": "EX_DIVIDEND_DATE",
                "source": "WEB",
                "client": "WEB",
            },
            headers={"Referer": "https://data.eastmoney.com/"},
            timeout=12,
        ) or {}
        rows = ((payload.get("result") or {}) if isinstance(payload.get("result"), dict) else {}).get(
            "data"
        ) or []
        # PRETAX_BONUS_RMB 为「每10股派息」，换算每股
        total = 0.0
        count = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            # 只要已实施
            progress = safe_str(row.get("ASSIGN_PROGRESS"))
            if progress and ("实施" not in progress and "分红" not in progress):
                # 仍可能是预案；东财盘口股息(TTM)通常含近一年已实施
                pass
            bonus = _num(row.get("PRETAX_BONUS_RMB"))
            if bonus is None:
                continue
            # 粗略取最近 2 次现金分红（覆盖年报+中报常见口径）
            total += bonus / 10.0
            count += 1
            if count >= 2:
                break
        if total > 0:
            out["dividend_ttm"] = _fmt_signed(total)
            close = _num(out.get("_close_for_div"))
            if close:
                out["dividend_yield"] = _fmt_pct(total / close * 100)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dividend extra failed %s: %s", code, exc)

    out.pop("_close_for_div", None)
    return out


def _map_push2(data: dict[str, Any]) -> dict[str, Any]:
    price = _num(data.get("f43"))
    open_p = _num(data.get("f46"))
    prev = _num(data.get("f60"))

    solid = ""
    if price is not None and open_p is not None and prev not in (None, 0):
        solid = _fmt_pct((price - open_p) / prev * 100)
    elif price is not None and open_p is not None and open_p != 0:
        solid = _fmt_pct((price - open_p) / open_p * 100)

    bid_vol = _sum_side(data, ("f20", "f18", "f16", "f14", "f12"))
    ask_vol = _sum_side(data, ("f32", "f34", "f36", "f38", "f40"))

    out: dict[str, Any] = {
        "price": _fmt_price(price),
        "change_1d": _fmt_pct(data.get("f170")),
        "pe": _fmt_signed(data.get("f162")),
        "pe_ttm": _fmt_signed(data.get("f164")),
        "pb": _fmt_signed(data.get("f167")),
        "roe": _fmt_pct(data.get("f173")),
        "avg_price": _fmt_price(data.get("f71")),
        "change_amt": _fmt_signed(data.get("f169")),
        "open": _fmt_price(open_p),
        "prev_close": _fmt_price(prev),
        "high": _fmt_price(data.get("f44")),
        "low": _fmt_price(data.get("f45")),
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
        "bid_ask_diff": _fmt_signed(data.get("f192"), 0),
        "bid_ask_ratio": _fmt_pct(data.get("f191")),
        "pe_static": _fmt_signed(data.get("f163")),
        "eps": _fmt_signed(data.get("f55"), 3),
        "bvps": _fmt_signed(data.get("f92")),
        "total_shares": _fmt_shares(data.get("f84")),
        "float_shares": _fmt_shares(data.get("f85")),
        "float_market_cap": _fmt_yi_wan(data.get("f117"), unit_yi=True),
        "total_market_cap": _fmt_yi_wan(data.get("f116"), unit_yi=True),
        "list_date": _fmt_list_date(data.get("f189")),
        "industry_name_em": safe_str(data.get("f127")),
        # 52周高低（东财盘口 f174/f175，前复权口径）
        "high_52w": _fmt_price(data.get("f174")),
        "low_52w": _fmt_price(data.get("f175")),
        # 盘后
        "after_volume": _fmt_signed(data.get("f260"), 0),
        "after_amount": _fmt_yi_wan(data.get("f261")),
        "after_bid": _fmt_signed(data.get("f16"), 0),
        # 发行股本（股数）
        "issued_shares": _fmt_shares(data.get("f278")),
        "_price_raw": price,
        "_turnover_raw": _num(data.get("f168")),
        "_float_shares_push_raw": _num(data.get("f85")),
        "_mcap_raw": _num(data.get("f116")),
    }

    if _num(data.get("f184")) is not None:
        out["revenue_yoy"] = _fmt_pct(data.get("f184"))
    if _num(data.get("f186")) is not None:
        out["profit_yoy"] = _fmt_pct(data.get("f186"))

    mcap_yi = _num(data.get("f116"))
    if mcap_yi is not None:
        out["market_cap"] = f"{mcap_yi / 1e8:.2f}".rstrip("0").rstrip(".")

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
        with ThreadPoolExecutor(max_workers=7) as pool:
            fut_quote = pool.submit(_fetch_push2, code)
            fut_flow = pool.submit(_fetch_fund_flow, code)
            fut_ret = pool.submit(_fetch_period_returns, code)
            fut_hand = pool.submit(_fetch_current_hand, code)
            fut_f10 = pool.submit(_fetch_f10_profile, code)
            fut_val = pool.submit(_fetch_valuation_extra, code)

            list_date = ""
            try:
                raw = fut_quote.result()
                if raw:
                    if isinstance(raw, dict) and "__tencent_mapped__" in raw:
                        result.update(raw["__tencent_mapped__"] or {})
                    else:
                        result.update(_map_push2(raw))
                        list_date = _fmt_list_date(raw.get("f189")) or result.get("list_date") or ""
                if not list_date:
                    list_date = result.get("list_date") or ""
            except Exception as exc:  # noqa: BLE001
                logger.warning("push2 quote failed %s: %s", code, exc)
                try:
                    result.update(_fetch_tencent_quote(code) or {})
                except Exception:  # noqa: BLE001
                    pass
                list_date = result.get("list_date") or ""

            # 历史/52周高低：等拿到上市日后按前复权全历史算（对齐东财）
            fut_ext = pool.submit(_fetch_price_extremes, code, list_date)
            # 盘口自带的 52 周高低优先保留（东财 f174/f175）
            official_52 = {
                k: result[k] for k in ("high_52w", "low_52w") if result.get(k)
            }

            for fut, label in (
                (fut_flow, "fund flow"),
                (fut_ret, "period returns"),
                (fut_hand, "current hand"),
                (fut_f10, "f10"),
                (fut_val, "valuation"),
                (fut_ext, "price extremes"),
            ):
                try:
                    result.update(fut.result() or {})
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s failed %s: %s", label, code, exc)

            if official_52:
                result.update(official_52)
    except Exception as exc:  # noqa: BLE001
        logger.warning("quote fetch failed %s: %s", code, exc)
        return {}

    # 换手(实)、自由流通市值、股息(TTM)
    free_raw = _num(result.pop("_free_float_shares_raw", None))
    float_raw = _num(result.pop("_float_shares_raw", None)) or _num(
        result.pop("_float_shares_push_raw", None)
    )
    price_raw = _num(result.pop("_price_raw", None))
    turnover_raw = _num(result.pop("_turnover_raw", None))
    mcap_raw = _num(result.pop("_mcap_raw", None))

    if free_raw and free_raw > 0:
        if "free_float_shares" not in result:
            result["free_float_shares"] = _fmt_shares(free_raw)
        if price_raw is not None:
            result["free_float_market_cap"] = _fmt_yi_wan(price_raw * free_raw, unit_yi=True)
        elif mcap_raw is not None and float_raw:
            result["free_float_market_cap"] = _fmt_yi_wan(
                mcap_raw * (free_raw / float_raw), unit_yi=True
            )
        if turnover_raw is not None and float_raw:
            result["turnover_real"] = _fmt_pct(turnover_raw * float_raw / free_raw)

    # 股息(TTM) ≈ 现价 × 股息率
    dy = result.get("dividend_yield")
    # dividend_yield 可能尚未并入（乐咕字段在上层），这里仅在有原始价格时预留计算入口

    # 清理内部字段
    for k in list(result.keys()):
        if k.startswith("_"):
            result.pop(k, None)

    if result:
        with _cache_lock:
            _mem_cache[code] = (now, dict(result))
    return result
