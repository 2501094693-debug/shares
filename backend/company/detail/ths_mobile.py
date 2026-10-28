"""同花顺手机端行情通道（``quota-h`` HTTP）的 Python 复刻。

同花顺 App / 网页行情在「成交明细」里走的是：

    POST https://quota-h.10jqka.com.cn/fuyao/common_hq_aggr/quote/v1/single_trace

请求体只包含 ``code_list`` / ``time_range`` / ``gpid``，不依赖登录态；
返回 ``data_fields`` + ``value`` 的紧凑列式数据。本模块按 App 的请求格式
原样发送，并把列式结果展开成逐条 dict，方便后端直接消费。

同一通道的另外两个接口也一并封装：

- ``multi_last_snapshot``：实时快照（App 盘口页）
- ``single_trend``：分时走势

注意：``single_trace`` 返回的是交易所 Level-1 的 3 秒成交快照（每行是
该 3 秒窗口内的聚合量），不是 Level-2 的单笔逐笔；同花顺 App 免费账号
看到的「成交明细」也是这一粒度。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta
from typing import Any, Iterable

import requests

from core.codes import detect_market, normalize_code
from core.fmt import to_float

logger = logging.getLogger(__name__)

BASE = "https://quota-h.10jqka.com.cn/fuyao/common_hq_aggr/quote/v1"
TRACE_URL = f"{BASE}/single_trace"
SNAPSHOT_URL = f"{BASE}/multi_last_snapshot"
TREND_URL = f"{BASE}/single_trend"

_TZ = timezone(timedelta(hours=8))
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": _UA,
    "Platform": "hxkline",
    "X-Auth-Type": "ths",
    "X-Auth-Version": "1.0",
    "X-Auth-ProgId": "7047",
    "X-Auth-AppName": "AINVEST",
}
_SIDE = {
    1: ("sell", "主卖"),
    2: ("buy", "主买"),
    3: ("neutral", "中性"),
}
# App 盘口页默认快照字段（价格/五档/量额等），需要别的字段时显式传 data_fields。
_SNAPSHOT_FIELDS = [
    "7", "8", "9", "10", "11", "13", "19", "24", "30", "6",
    "264648", "199112", "1968584", "3153", "3541450", "3475914",
    "1771976", "65551",
]


class ThsMobileError(RuntimeError):
    """同花顺手机端接口返回非 0 状态码。"""


def market_of(code: str) -> str:
    """股票代码 → 同花顺 ``quota-h`` 的 market 编号。

    App 里 ``600519`` 是 ``17``，``000001`` 是 ``33``，北交所是 ``144``；
    指数/板块不在本模块的股票场景内。
    """
    norm = normalize_code(code)
    if not norm:
        return ""
    market = detect_market(norm)
    if market == "sse":
        return "17"
    if market == "szse":
        return "33"
    if market == "bse":
        return "144"
    # detect_market 没覆盖 ETF / 基金 / 老代码，按首位兜底
    if norm.startswith(("5", "6", "9")):
        return "17"
    if norm.startswith(("0", "1", "2", "3")):
        return "33"
    if norm.startswith(("4", "8")):
        return "144"
    return ""


def _code_list(code: str) -> tuple[str, str, list[dict[str, Any]]]:
    norm = normalize_code(code)
    market = market_of(norm)
    if not norm or not market:
        raise ValueError("无效股票代码")
    return norm, market, [{"codes": [norm], "market": market}]


def _end_time_ms(value: Any) -> int:
    """``0`` 表示最新；``datetime`` / ISO 字符串 / 毫秒时间戳统一成毫秒。"""
    if value in (None, "", 0, "0"):
        return 0
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=_TZ)
        return int(stamp.timestamp() * 1000)
    if isinstance(value, date):
        return int(datetime(value.year, value.month, value.day, tzinfo=_TZ).timestamp() * 1000)
    text = str(value).strip()
    if text.isdigit():
        number = int(text)
        return number * 1000 if number < 10_000_000_000 else number
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_TZ)
    return int(parsed.timestamp() * 1000)


def _post(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: float = 10.0,
    referer: str = "https://stockpage.10jqka.com.cn/600519/stock-quote/",
) -> dict[str, Any]:
    headers = dict(_HEADERS)
    headers["Referer"] = referer
    headers["Origin"] = "https://stockpage.10jqka.com.cn"
    session = requests.Session()
    session.trust_env = False
    try:
        resp = session.post(url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
    finally:
        session.close()
    if not isinstance(body, dict):
        raise ThsMobileError("同花顺手机端返回非 JSON 对象")
    if body.get("status_code") not in (0, "0", None):
        raise ThsMobileError(
            f"同花顺手机端 status_code={body.get('status_code')}: {body.get('status_msg')}"
        )
    return body


def _parse_trace(code: str, quote: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [str(name) for name in (quote.get("data_fields") or [])]
    index = {name: pos for pos, name in enumerate(fields)}
    rows = quote.get("value") or []
    if not isinstance(rows, list):
        return []

    def cell(row: list[Any], name: str) -> Any:
        pos = index.get(name)
        if pos is None or pos >= len(row):
            return None
        return row[pos]

    out: list[dict[str, Any]] = []
    prev_cum: float | None = None
    for seq, row in enumerate(rows):
        if not isinstance(row, (list, tuple)):
            continue
        stamp_ms = to_float(cell(row, "1"))
        price = to_float(cell(row, "10"))
        if stamp_ms is None or price is None:
            continue
        volume = to_float(cell(row, "49"))
        cum_volume = to_float(cell(row, "13"))
        if volume is None and cum_volume is not None and prev_cum is not None:
            volume = cum_volume - prev_cum
        if cum_volume is not None:
            prev_cum = cum_volume
        volume = volume or 0.0

        direction = cell(row, "12")
        try:
            deal_type = int(float(direction))
        except (TypeError, ValueError):
            deal_type = -1
        side, side_label = _SIDE.get(deal_type, ("", ""))

        stamp = datetime.fromtimestamp(stamp_ms / 1000.0, _TZ)
        text = stamp.strftime("%Y-%m-%d %H:%M:%S")
        out.append(
            {
                "time": text,
                "stamp": text[11:],
                "code": code,
                "price": price,
                "volume": volume,
                "volume_lots": round(volume / 100.0, 2),
                "amount": round(price * volume, 2),
                "side": side,
                "side_label": side_label,
                "deal_type": deal_type,
                "cum_volume": cum_volume,
                "seq": seq,
                "event_id": f"{int(stamp_ms)}|{int(cum_volume or 0)}|{seq}",
            }
        )
    return out


def fetch_trace(
    code: str,
    *,
    count: int = 60,
    end_time: Any = 0,
    gpid: int = 1,
    timeout: float = 10.0,
    raw: bool = False,
) -> list[dict[str, Any]] | dict[str, Any]:
    """拉取成交明细（App 的「逐笔/成交明细」通道）。

    - ``count``：最近 N 条（3 秒快照），上限按接口实际返回为准。
    - ``end_time``：``0`` 为最新；也可传 ``datetime`` / ISO 字符串 / 毫秒时间戳。
    - ``raw=True``：返回原始 JSON，便于排查字段变化。
    """
    norm, _market, codes = _code_list(code)
    payload = {
        "code_list": codes,
        "time_range": {
            "type": "end_count",
            "count": max(1, min(int(count), 1000)),
            "end_time": _end_time_ms(end_time),
        },
        "gpid": int(gpid),
    }
    body = _post(
        TRACE_URL,
        payload,
        timeout=timeout,
        referer=f"https://stockpage.10jqka.com.cn/{norm}/stock-quote/",
    )
    if raw:
        return body

    items: list[dict[str, Any]] = []
    quote_data = (body.get("data") or {}).get("quote_data") or []
    for quote in quote_data:
        if isinstance(quote, dict):
            items.extend(_parse_trace(norm, quote))
    items.sort(key=lambda row: (row["time"], row["seq"]))
    if not items:
        logger.info("ths mobile trace empty %s count=%s end=%s", norm, count, end_time)
    return items


fetch_ticks = fetch_trace


def fetch_snapshot(
    codes: str | Iterable[str],
    *,
    trade_class: str = "intraday",
    data_fields: Iterable[str] | None = None,
    gpid: int = 1,
    timeout: float = 10.0,
    raw: bool = False,
) -> list[dict[str, Any]] | dict[str, Any]:
    """实时快照（App 盘口页的 ``multi_last_snapshot``）。

    ``codes`` 可传单只或多只；返回 ``quote_data`` 原始列式结构，字段名
    见 ``data_fields``（默认与 App 盘口页一致）。
    """
    if isinstance(codes, str):
        codes = [codes]
    grouped: dict[str, list[str]] = {}
    for code in codes:
        norm = normalize_code(code)
        market = market_of(norm)
        if not norm or not market:
            continue
        grouped.setdefault(market, []).append(norm)
    if not grouped:
        raise ValueError("无效股票代码")
    payload = {
        "code_list": [
            {"codes": sorted(set(items)), "market": market}
            for market, items in grouped.items()
        ],
        "trade_class": trade_class,
        "data_fields": [str(field) for field in (data_fields or _SNAPSHOT_FIELDS)],
        "lang": "zh_cn",
        "gpid": int(gpid),
    }
    first = next(iter(grouped.values()))[0]
    body = _post(
        SNAPSHOT_URL,
        payload,
        timeout=timeout,
        referer=f"https://stockpage.10jqka.com.cn/{first}/stock-quote/",
    )
    if raw:
        return body
    return (body.get("data") or {}).get("quote_data") or []


def fetch_trend(
    code: str,
    *,
    trade_date: int = 0,
    trade_class: str = "intraday",
    gpid: int = 1,
    timeout: float = 10.0,
    raw: bool = False,
) -> list[dict[str, Any]] | dict[str, Any]:
    """分时走势（App 分时图通道）。"""
    norm, _market, codes = _code_list(code)
    payload = {
        "code_list": codes,
        "trade_class": trade_class,
        "trade_date": int(trade_date),
        "gpid": int(gpid),
    }
    body = _post(
        TREND_URL,
        payload,
        timeout=timeout,
        referer=f"https://stockpage.10jqka.com.cn/{norm}/stock-quote/",
    )
    if raw:
        return body
    return (body.get("data") or {}).get("quote_data") or []
