"""个股盘口的各数据源。

``company.statistics.fetcher.fetch_stock_quote`` 并行调用这里的函数，再拼成一张字段表。
单个源失败返回 ``{}``，不抛给上层，由编排层用乐咕成分股字段兜底。

数据源分工：
- 实时盘口：东财 push2，失败再腾讯 qt.gtimg.cn
- 区间涨幅：``company.statistics.period_returns.fetch_period_returns``（腾讯日 K 优先，东财补充）
- 历史/52 周高低：腾讯前复权日 K（按年并行）
- 现手：``company.line.fetcher.fetch_ticks`` 最近一笔
- F10：注册资本、发行股本
- 自由流通：``company.statistics.free_float``
- 估值：市销率、近一年现金分红 → 股息(TTM)
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from core.codes import em_code, secid, tencent_symbol
from core.fmt import (
    drop_empty,
    fmt_list_date,
    fmt_pct,
    fmt_price,
    fmt_shares,
    fmt_signed,
    fmt_volume_hands,
    fmt_yi_wan,
    to_float,
)
from core.http import get_json, get_text
from company.line.fetcher import fetch_ticks as fetch_kline_ticks
from company.statistics.period_returns import fetch_period_returns as fetch_kline_period_returns
from company.statistics.free_float import calc as calc_free_float
from core.codes import normalize_code, safe_str

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 东财 push2
# ---------------------------------------------------------------------------

_PUSH2_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
    "https://71.push2.eastmoney.com",
)

# 盘口字段清单：价格/估值/涨跌/盘口档位/股本/52 周高低等，一次拉齐
_PUSH2_FIELDS = (
    "f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f55,f57,f58,f60,f71,"
    "f84,f85,f92,f116,f117,f127,f161,f162,f163,f164,f167,f168,f169,f170,"
    "f171,f173,f174,f175,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,"
    "f198,f199,f260,f261,f277,f278,"
    "f11,f12,f13,f14,f15,f16,f17,f18,f19,f20,"
    "f31,f32,f33,f34,f35,f36,f37,f38,f39,f40"
)

_RETURN_KEYS = (
    "change_3d",
    "change_5d",
    "change_10d",
    "change_20d",
    "change_60d",
    "change_half_year",
    "change_1y",
    "change_ytd",
)


@dataclass
class RealtimeQuote:
    """实时盘口拉取结果。

    source:
      - ``eastmoney``：``raw`` 是 push2 原始字段，调用方再 ``map_push2``
      - ``tencent``：``mapped`` 已是规范化字段（东财不可用时的回退）
      - ``""``：两边都失败
    """

    source: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    mapped: dict[str, Any] = field(default_factory=dict)


def _sum_side(data: dict[str, Any], vol_keys: tuple[str, ...]) -> float | None:
    """买卖五档量加总。全部缺失返回 None，而不是 0。"""
    total = 0.0
    ok = False
    for key in vol_keys:
        number = to_float(data.get(key))
        if number is None:
            continue
        total += number
        ok = True
    return total if ok else None


def fetch_tencent_quote(code: str) -> dict[str, Any]:
    """腾讯实时行情。东财 push2 不可用时的回退。

    返回已格式化的字段（与 ``map_push2`` 子集对齐），没有的键直接省略。
    """
    symbol = tencent_symbol(code)
    text = get_text(
        "https://qt.gtimg.cn/q=" + symbol,
        headers={"Referer": "https://gu.qq.com/"},
        timeout=10,
    )
    # v_sh601881="1~名称~代码~现价~昨收~今开~总量~外盘~内盘~..."
    if '="' not in text:
        return {}
    body = text.split('="', 1)[1].rsplit('"', 1)[0]
    parts = body.split("~")
    if len(parts) < 45:
        return {}

    price = to_float(parts[3])
    prev = to_float(parts[4])
    open_p = to_float(parts[5])
    volume = to_float(parts[6])
    outer = to_float(parts[7])
    inner = to_float(parts[8])
    change_amt = to_float(parts[31]) if len(parts) > 31 else None
    change_pct = to_float(parts[32]) if len(parts) > 32 else None
    high = to_float(parts[33]) if len(parts) > 33 else None
    low = to_float(parts[34]) if len(parts) > 34 else None
    amount_wan = to_float(parts[37]) if len(parts) > 37 else None
    turnover = to_float(parts[38]) if len(parts) > 38 else None
    float_mcap_yi = to_float(parts[44]) if len(parts) > 44 else None
    mcap_yi = to_float(parts[45]) if len(parts) > 45 else None

    solid = ""
    if price is not None and open_p is not None and prev not in (None, 0):
        solid = fmt_pct((price - open_p) / prev * 100)

    out: dict[str, Any] = {
        "price": fmt_price(price),
        "prev_close": fmt_price(prev),
        "open": fmt_price(open_p),
        "high": fmt_price(high),
        "low": fmt_price(low),
        "volume": fmt_volume_hands(volume),
        "outer_vol": fmt_volume_hands(outer),
        "inner_vol": fmt_volume_hands(inner),
        "change_amt": fmt_signed(change_amt),
        "change_1d": fmt_pct(change_pct),
        "solid_change": solid,
        "turnover": fmt_pct(turnover),
        "amount": fmt_yi_wan((amount_wan or 0) * 1e4) if amount_wan is not None else "",
        "_price_raw": price,
        "_turnover_raw": turnover,
    }
    if mcap_yi is not None:
        out["market_cap"] = f"{mcap_yi:.2f}".rstrip("0").rstrip(".")
        out["total_market_cap"] = f"{out['market_cap']}亿"
    if float_mcap_yi is not None:
        text = f"{float_mcap_yi:.2f}".rstrip("0").rstrip(".")
        out["float_market_cap"] = f"{text}亿"
    if high is not None and low is not None and prev not in (None, 0):
        out["amplitude"] = fmt_pct((high - low) / prev * 100)
    return drop_empty(out)


def fetch_realtime_quote(code: str) -> RealtimeQuote:
    """东财 push2 优先；全部 host 失败再腾讯。不抛异常。"""
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": _PUSH2_FIELDS,
        "secid": secid(code),
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    }
    headers = {
        "Referer": f"https://quote.eastmoney.com/sh{normalize_code(code)}.html"
    }
    last_exc: Exception | None = None
    for host in _PUSH2_HOSTS:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/get",
                params=params,
                headers=headers,
                timeout=10,
            ) or {}
            data = payload.get("data")
            if isinstance(data, dict) and data:
                return RealtimeQuote(source="eastmoney", raw=data)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue

    try:
        tx = fetch_tencent_quote(code)
        if tx:
            logger.info("push2 fallback to tencent quote for %s", code)
            return RealtimeQuote(source="tencent", mapped=tx)
    except Exception as exc:  # noqa: BLE001
        logger.info("tencent quote fallback failed %s: %s", code, exc)
    if last_exc:
        logger.info("push2 unavailable %s: %s", code, last_exc)
    return RealtimeQuote()


def map_push2(data: dict[str, Any]) -> dict[str, Any]:
    """东财 push2 原始字段 → 公司详情页用的规范化 dict。

    带 ``_`` 前缀的是给编排层算自由流通市值 / 换手(实) 用的中间值，返回前会清掉。
    """
    price = to_float(data.get("f43"))
    open_p = to_float(data.get("f46"))
    prev = to_float(data.get("f60"))

    solid = ""
    if price is not None and open_p is not None and prev not in (None, 0):
        solid = fmt_pct((price - open_p) / prev * 100)
    elif price is not None and open_p is not None and open_p != 0:
        solid = fmt_pct((price - open_p) / open_p * 100)

    bid_vol = _sum_side(data, ("f20", "f18", "f16", "f14", "f12"))
    ask_vol = _sum_side(data, ("f32", "f34", "f36", "f38", "f40"))

    out: dict[str, Any] = {
        "price": fmt_price(price),
        "change_1d": fmt_pct(data.get("f170")),
        "pe": fmt_signed(data.get("f162")),
        "pe_ttm": fmt_signed(data.get("f164")),
        "pb": fmt_signed(data.get("f167")),
        "roe": fmt_pct(data.get("f173")),
        "avg_price": fmt_price(data.get("f71")),
        "change_amt": fmt_signed(data.get("f169")),
        "open": fmt_price(open_p),
        "prev_close": fmt_price(prev),
        "high": fmt_price(data.get("f44")),
        "low": fmt_price(data.get("f45")),
        "volume": fmt_volume_hands(data.get("f47")),
        "amount": fmt_yi_wan(data.get("f48")),
        "turnover": fmt_pct(data.get("f168")),
        "volume_ratio": fmt_signed(data.get("f50")),
        "amplitude": fmt_pct(data.get("f171")),
        "solid_change": solid,
        "limit_up": fmt_price(data.get("f51")),
        "limit_down": fmt_price(data.get("f52")),
        "outer_vol": fmt_volume_hands(data.get("f49")),
        "inner_vol": fmt_volume_hands(data.get("f161")),
        "bid_vol": fmt_signed(bid_vol, 0) if bid_vol is not None else "",
        "ask_vol": fmt_signed(ask_vol, 0) if ask_vol is not None else "",
        "bid_ask_diff": fmt_signed(data.get("f192"), 0),
        "bid_ask_ratio": fmt_pct(data.get("f191")),
        "pe_static": fmt_signed(data.get("f163")),
        "eps": fmt_signed(data.get("f55"), 3),
        "bvps": fmt_signed(data.get("f92")),
        "total_shares": fmt_shares(data.get("f84")),
        "float_shares": fmt_shares(data.get("f85")),
        "float_market_cap": fmt_yi_wan(data.get("f117"), unit_yi=True),
        "total_market_cap": fmt_yi_wan(data.get("f116"), unit_yi=True),
        "list_date": fmt_list_date(data.get("f189")),
        "industry_name_em": safe_str(data.get("f127")),
        "high_52w": fmt_price(data.get("f174")),
        "low_52w": fmt_price(data.get("f175")),
        "after_volume": fmt_signed(data.get("f260"), 0),
        "after_amount": fmt_yi_wan(data.get("f261")),
        "after_bid": fmt_signed(data.get("f16"), 0),
        "issued_shares": fmt_shares(data.get("f278")),
        "_price_raw": price,
        "_turnover_raw": to_float(data.get("f168")),
        "_float_shares_push_raw": to_float(data.get("f85")),
        "_mcap_raw": to_float(data.get("f116")),
    }

    if to_float(data.get("f184")) is not None:
        out["revenue_yoy"] = fmt_pct(data.get("f184"))
    if to_float(data.get("f186")) is not None:
        out["profit_yoy"] = fmt_pct(data.get("f186"))

    mcap_yi = to_float(data.get("f116"))
    if mcap_yi is not None:
        out["market_cap"] = f"{mcap_yi / 1e8:.2f}".rstrip("0").rstrip(".")

    return drop_empty(out)


# ---------------------------------------------------------------------------
# 区间涨幅 / 现手 / 自由流通
# ---------------------------------------------------------------------------


def fetch_period_returns(code: str) -> dict[str, Any]:
    """区间涨幅。走 ``company.statistics.period_returns.fetch_period_returns``（腾讯日 K 优先）。"""
    try:
        pack = fetch_kline_period_returns(code, adjust="qfq")
    except Exception as exc:  # noqa: BLE001
        logger.info("period returns skip %s: %s", code, exc)
        return {}
    return {key: pack[key] for key in _RETURN_KEYS if pack.get(key)}


def fetch_current_hand(code: str) -> dict[str, Any]:
    """现手：最近一笔成交量（手）。"""
    try:
        pack = fetch_kline_ticks(code, pos=-20)
    except Exception as exc:  # noqa: BLE001
        logger.info("current hand skip %s: %s", code, exc)
        return {}
    items = pack.get("items") or []
    if not items:
        return {}
    vol = to_float(items[-1].get("volume"))
    if vol is None:
        return {}
    return {"current_volume": fmt_signed(vol, 0)}


def fetch_free_float_fields(code: str) -> dict[str, Any]:
    """自由流通股中间值，供编排层算市值 / 换手(实)。"""
    try:
        data = calc_free_float(code)
    except Exception as exc:  # noqa: BLE001
        logger.info("free float skip %s: %s", code, exc)
        return {}
    free = to_float(data.get("free_float_shares"))
    if not free or free <= 0:
        return {}
    out: dict[str, Any] = {
        "free_float_shares": data.get("free_float_shares_fmt") or fmt_shares(free),
        "_free_float_shares_raw": free,
        "_float_shares_raw": data.get("float_shares"),
    }
    cap_fmt = data.get("free_float_market_cap_fmt")
    if cap_fmt:
        out["free_float_market_cap"] = cap_fmt
    return out


# ---------------------------------------------------------------------------
# 历史 / 52 周最高最低
# ---------------------------------------------------------------------------


def fetch_tencent_day_rows(
    symbol: str,
    *,
    start: str = "",
    end: str = "",
    limit: int = 640,
    qfq: bool = False,
) -> list[list[Any]]:
    """腾讯日 K。``qfq=True`` 为前复权（历史高低对齐东财盘口）。"""
    adj = "qfq" if qfq else ""
    if start and end:
        param = f"{symbol},day,{start},{end},{limit},{adj}"
    else:
        param = f"{symbol},day,,,{limit},{adj}"
    payload: dict[str, Any] = {}
    for url in (
        "https://ifzq.gtimg.cn/appstock/app/fqkline/get",
        "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
    ):
        try:
            pack = get_json(
                url,
                params={"param": param},
                headers={"Referer": "https://gu.qq.com/"},
                timeout=12,
            ) or {}
        except Exception:  # noqa: BLE001
            continue
        if isinstance(pack, dict) and pack.get("data"):
            payload = pack
            break
    node = ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get(
        symbol
    ) or {}
    rows = node.get("qfqday") if qfq else node.get("day")
    if not rows:
        rows = node.get("qfqday") or node.get("day") or []
    return rows if isinstance(rows, list) else []


def fetch_price_extremes(code: str, list_date: str = "") -> dict[str, Any]:
    """52 周 / 历史最高最低：前复权全历史，口径对齐东财盘口。

    腾讯单次日 K 约 640 根，长区间会被截成最近一段，因此按年并行拉取。
    部分老股前复权会出现 ≤0 的异常价，有效样本不足或不合理时回退不复权。
    """
    symbol = tencent_symbol(code)
    start_year = 1990
    ld = (list_date or "").replace("-", "").replace("/", "")
    if len(ld) >= 4 and ld[:4].isdigit():
        start_year = max(1990, int(ld[:4]))
    end_year = time.localtime().tm_year

    ranges = [
        (f"{y:04d}-01-01", f"{y:04d}-12-31")
        for y in range(start_year, end_year + 1)
    ]

    def _pull(span: tuple[str, str], qfq: bool) -> list[list[Any]]:
        start, end = span
        try:
            return fetch_tencent_day_rows(symbol, start=start, end=end, limit=640, qfq=qfq)
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
                for row in fetch_tencent_day_rows(symbol, limit=640, qfq=qfq):
                    if isinstance(row, (list, tuple)) and len(row) >= 5:
                        by_date[str(row[0])[:10]] = list(row)
            except Exception as exc:  # noqa: BLE001
                logger.info("extremes fallback skip %s qfq=%s: %s", code, qfq, exc)
        return [by_date[k] for k in sorted(by_date)]

    def _minmax(
        rows: list[list[Any]], *, min_price: float = 0.0
    ) -> tuple[float | None, float | None, int, int]:
        """返回 (high, low, 有效根数, 被过滤根数)。"""
        highs: list[float] = []
        lows: list[float] = []
        dropped = 0
        for row in rows:
            high = to_float(row[3])
            low = to_float(row[4])
            if high is None or low is None:
                continue
            if high <= min_price or low <= min_price:
                dropped += 1
                continue
            highs.append(high)
            lows.append(low)
        if not highs or not lows:
            return None, None, 0, dropped
        return max(highs), min(lows), len(highs), dropped

    qfq_rows = _collect(True)
    if len(qfq_rows) < 5:
        return {}

    high_all, low_all, kept, dropped = _minmax(qfq_rows, min_price=0.0)
    use_rows = qfq_rows
    if high_all is None or low_all is None:
        return {}

    bad_ratio = dropped / max(1, kept + dropped)
    if bad_ratio >= 0.05:
        raw_rows = _collect(False)
        raw_high, raw_low, raw_kept, _ = _minmax(raw_rows, min_price=0.0)
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
        "high_all": fmt_price(high_all),
        "low_all": fmt_price(low_all),
    }
    window = min(252, len(use_rows))
    h52, l52, _, _ = _minmax(use_rows[-window:], min_price=0.0)
    if h52 is not None:
        out["high_52w"] = fmt_price(h52)
    if l52 is not None:
        out["low_52w"] = fmt_price(l52)
    return out


# ---------------------------------------------------------------------------
# F10 股本 / 估值
# ---------------------------------------------------------------------------


def _first_dict(node: Any) -> dict[str, Any]:
    """F10 接口同一字段有时是 dict、有时是单元素 list。"""
    if isinstance(node, list):
        node = node[0] if node else {}
    return node if isinstance(node, dict) else {}


def fetch_f10_profile(code: str) -> dict[str, Any]:
    """注册资本、发行股本。自由流通股由 ``fetch_free_float_fields`` 另算。"""
    em = em_code(code)
    out: dict[str, Any] = {}
    headers = {
        "Referer": (
            "https://emweb.securities.eastmoney.com/"
            f"PC_HSF10/CompanySurvey/Index?type=web&code={em}"
        ),
        "Accept": "application/json, text/plain, */*",
    }

    try:
        survey = get_json(
            "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax",
            params={"code": em},
            headers=headers,
            timeout=15,
        ) or {}
        jb = _first_dict(survey.get("jbzl"))
        zczb = safe_str(jb.get("zczb"))
        if zczb and zczb != "--":
            out["registered_capital"] = zczb
        fxxg = _first_dict(survey.get("fxxg"))
        fxl = safe_str(fxxg.get("fxl"))
        if fxl and fxl != "--":
            out["issued_shares"] = fxl
    except Exception as exc:  # noqa: BLE001
        logger.warning("F10 survey failed %s: %s", code, exc)

    return out


def fetch_valuation_extra(code: str) -> dict[str, Any]:
    """市销率、股息(TTM)。股息按近两次已披露现金分红（每 10 股派息 / 10）粗算。"""
    c = normalize_code(code)
    out: dict[str, Any] = {}
    try:
        payload = get_json(
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
        rows = (
            ((payload.get("result") or {}) if isinstance(payload.get("result"), dict) else {}).get(
                "data"
            )
            or []
        )
        if rows:
            row = rows[0]
            ps = to_float(row.get("PS_TTM"))
            if ps is not None:
                out["ps_ttm"] = fmt_signed(ps)
            price = to_float(row.get("CLOSE_PRICE"))
            if price is not None:
                out["_close_for_div"] = price
    except Exception as exc:  # noqa: BLE001
        logger.warning("valuation extra failed %s: %s", code, exc)

    try:
        payload = get_json(
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
        rows = (
            ((payload.get("result") or {}) if isinstance(payload.get("result"), dict) else {}).get(
                "data"
            )
            or []
        )
        total = 0.0
        count = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            bonus = to_float(row.get("PRETAX_BONUS_RMB"))
            if bonus is None:
                continue
            total += bonus / 10.0
            count += 1
            if count >= 2:
                break
        if total > 0:
            out["dividend_ttm"] = fmt_signed(total)
            close = to_float(out.get("_close_for_div"))
            if close:
                out["dividend_yield"] = fmt_pct(total / close * 100)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dividend extra failed %s: %s", code, exc)

    out.pop("_close_for_div", None)
    return out
