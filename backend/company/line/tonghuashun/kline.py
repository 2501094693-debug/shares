"""同花顺日 K 及多周期 K 线（官方 ``thsdk``，需实盘扫码登录）。

数据路径：``thsdk.klines``（传统 K 线查询，返回 ``pandas.DataFrame``，
``time`` 为索引：日线 ``YYYYMMDD``，分钟线 ``YYYYMMDDHHMM``）。

- ``ths_code`` 格式为 4 位市场 + 代码，如 ``USHA600519`` / ``USZA000001``，
  由 ``company.statistics.fundflow.tonghuashun.hq.hq_security`` 生成。
- 周期 ``interval``：``day/week/month/quarter/year`` 及 ``1m/5m/15m/30m/60m/120m``。
- 复权 ``fq``：``""`` / ``none`` 不复权，``pre`` 前复权（默认），``post`` 后复权。
- ``count`` 与日期区间互斥；分钟线只支持 ``count``，不支持日期区间。

对外签名与 ``company.line.tencent.kline`` / ``company.line.eastmoney.kline``
对齐：``fetch_line`` / ``fetch_lines``，返回统一 K 线包
``{code, name, period, adjust, pre_price, source, count, items}``，
``items`` 每根为 ``{time, open, close, high, low, volume, amount,
change, pct_chg, amplitude, turnover}``（缺的键为 ``None``）。

    python -m company.line.tonghuashun.kline 600519
    python -m company.line.tonghuashun.kline 600519 --period week --limit 5
    python -m company.line.tonghuashun.kline 600519 --period 5m --limit 10
    python -m company.line.tonghuashun.kline 600519 --beg 20240101 --end 20241231
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

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import normalize_code
from core.fmt import to_float


def _hq_security(code: str) -> str:
    """HQ 证券代码（``USHA600519`` 格式），延迟导入以避开循环引用。"""
    from company.statistics.fundflow.tonghuashun import hq as _hq

    return _hq.hq_security(code)

logger = logging.getLogger(__name__)

# 规范名 → thsdk interval。分钟线只支持 count，不支持日期区间。
PERIOD_INTERVAL: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "60m": "60m",
    "120m": "120m",
    "day": "day",
    "week": "week",
    "month": "month",
    "quarter": "quarter",
    "year": "year",
}
MINUTE_PERIODS: tuple[str, ...] = ("1m", "5m", "15m", "30m", "60m", "120m")
BAR_PERIODS: tuple[str, ...] = ("day", "week", "month", "quarter", "year")
ALL_PERIODS: tuple[str, ...] = MINUTE_PERIODS + BAR_PERIODS
DEFAULT_PERIODS: tuple[str, ...] = ("day", "week", "month")

_PERIOD_ALIASES: dict[str, str] = {
    "1": "1m", "1m": "1m", "1min": "1m", "min1": "1m",
    "5": "5m", "5m": "5m", "5min": "5m",
    "15": "15m", "15m": "15m", "15min": "15m",
    "30": "30m", "30m": "30m", "30min": "30m",
    "60": "60m", "60m": "60m", "60min": "60m", "1h": "60m", "hour": "60m",
    "120": "120m", "120m": "120m", "2h": "120m",
    "101": "day", "day": "day", "d": "day", "daily": "day",
    "102": "week", "week": "week", "w": "week", "weekly": "week",
    "103": "month", "month": "month", "m": "month", "monthly": "month",
    "104": "quarter", "quarter": "quarter", "q": "quarter",
    "season": "quarter", "qtr": "quarter",
    "106": "year", "year": "year", "y": "year", "yearly": "year", "annual": "year",
}
_ADJUST_FQ = {
    "0": "", "none": "", "n": "",
    "1": "pre", "qfq": "pre", "forward": "pre", "pre": "pre",
    "2": "post", "hfq": "post", "backward": "post", "post": "post",
}
_ADJUST_LABEL = {"": "none", "pre": "qfq", "post": "hfq"}


_UNSUPPORTED = {
    **dict.fromkeys(("105", "halfyear", "half", "hy", "h", "semiannual"), "同花顺不支持半年 K"),
}


def _period(period: str) -> str:
    key = (period or "day").strip().lower()
    if key in _UNSUPPORTED:
        raise ValueError(_UNSUPPORTED[key])
    if key in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[key]
    if key in PERIOD_INTERVAL:
        return key
    raise ValueError(
        "period 须为 1m|5m|15m|30m|60m|120m|day|week|month|quarter|year"
    )


def _adjust(adjust: str | int) -> str:
    key = str(adjust if adjust is not None else "qfq").strip().lower()
    if key not in _ADJUST_FQ:
        raise ValueError("adjust 须为 none|qfq|hfq（或 0|1|2）")
    return _ADJUST_FQ[key]


def _date(value: str) -> str:
    text = (value or "").replace("-", "").replace("/", "").strip()
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return text
    raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")


def _fmt_time(raw: Any, *, minute: bool) -> str:
    text = re.sub(r"\D", "", str(raw or ""))
    if minute and len(text) >= 12:
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]} {text[8:10]}:{text[10:12]}"
    if len(text) >= 8:
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return str(raw or "").strip()


def _row_get(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        if key in lowered:
            return lowered[key]
    return None


def _parse_row(row: dict[str, Any], *, minute: bool) -> dict[str, Any] | None:
    open_ = to_float(_row_get(row, "open", "openprice", "open_price"))
    close = to_float(_row_get(row, "close", "closeprice", "close_price"))
    high = to_float(_row_get(row, "high", "highprice", "high_price", "max"))
    low = to_float(_row_get(row, "low", "lowprice", "low_price", "min"))
    if close is None and open_ is None:
        return None
    return {
        "time": _fmt_time(_row_get(row, "time", "date", "datetime"), minute=minute),
        "open": open_,
        "close": close,
        "high": high,
        "low": low,
        "volume": to_float(_row_get(row, "volume", "vol", "dealvolume")),
        "amount": to_float(_row_get(row, "amount", "turnover", "dealamount", "money")),
        "change": to_float(_row_get(row, "change", "pricechange", "updown")),
        "pct_chg": to_float(_row_get(row, "pct_chg", "pctchange", "changepercent", "涨跌幅")),
        "amplitude": to_float(_row_get(row, "amplitude", "zhenfu", "振幅")),
        "turnover": to_float(_row_get(row, "turnover", "turnoverrate", "换手", "换手率")),
    }


def _fill_change(items: list[dict[str, Any]]) -> None:
    """缺涨跌额 / 涨跌幅 / 振幅时，用上一根有效收盘补。"""
    prev: float | None = None
    for item in items:
        close = to_float(item.get("close"))
        high = to_float(item.get("high"))
        low = to_float(item.get("low"))
        if prev not in (None, 0):
            if close is not None:
                item.setdefault("change", round(close - prev, 4))
                item.setdefault("pct_chg", round((close / prev - 1.0) * 100, 4))
            if (
                high is not None
                and low is not None
                and item.get("amplitude") is None
            ):
                item["amplitude"] = round((high - low) / prev * 100, 4)
        prev = close if close is not None else prev


def fetch_line(
    code: str,
    *,
    period: str = "day",
    adjust: str | int = "qfq",
    limit: int = 320,
    beg: str = "",
    end: str = "",
) -> dict[str, Any]:
    """从同花顺拉一根周期的 K 线（需 thsdk 扫码登录）。

    period: 1m|5m|15m|30m|60m|120m|day|week|month|quarter|year
    adjust: none|qfq|hfq（或 0|1|2），默认前复权。
    不传 ``beg`` 时按最近 ``limit`` 根拉；传了 ``beg`` 则按日期区间
    （仅日及以上周期；分钟线不支持区间，会抛 ``ValueError``）。
    未登录时抛 ``RuntimeError``，由上层 fallback 到东财 / 腾讯。
    """
    import thsdk

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    canon = _period(period)
    fq = _adjust(adjust)
    minute = canon in MINUTE_PERIODS

    cap = int(limit) if limit is not None else 320
    cap = max(1, min(cap if cap > 0 else 10000, 10000))

    beg_s = _date(beg)
    end_s = _date(end)

    security = _hq_security(norm)
    if not security:
        raise ValueError("无效股票代码")
    if not thsdk.auth_qrcode(timeout=10):
        raise RuntimeError("thsdk 会话复用失败，请重新扫码登录")

    interval = PERIOD_INTERVAL[canon]
    if beg_s or end_s:
        if minute:
            raise ValueError("同花顺分钟 K 不支持日期区间，请用 limit")
        frame = thsdk.klines(
            security,
            start_time=beg_s or None,
            end_time=end_s or None,
            adjust=fq,
            interval=interval,
        )
        query = "range"
    else:
        frame = thsdk.klines(security, adjust=fq, interval=interval, count=cap)
        query = "last"

    try:
        records = frame.reset_index().to_dict("records")
    except Exception:  # noqa: BLE001
        records = list(frame.to_dict("records")) if hasattr(frame, "to_dict") else []
    items: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        parsed = _parse_row(record, minute=minute)
        if parsed and parsed.get("time"):
            items.append(parsed)
    items.sort(key=lambda r: str(r.get("time") or ""))
    if query == "last" and len(items) > cap:
        items = items[-cap:]
    _fill_change(items)

    return {
        "code": norm,
        "security": security,
        "name": "",
        "period": canon,
        "interval": interval,
        "adjust": _ADJUST_LABEL.get(fq, "none"),
        "query": query,
        "pre_price": None,
        "source": "tonghuashun" if items else "",
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
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    canon = [_period(period) for period in (periods or DEFAULT_PERIODS)]
    result: dict[str, Any] = {
        "code": norm,
        "name": "",
        "adjust": _ADJUST_LABEL.get(_adjust(adjust), "none"),
        "source": "tonghuashun",
    }
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(canon)))) as pool:
        futs = {
            period: pool.submit(
                fetch_line, code, period=period, adjust=adjust,
                limit=limit, beg=beg, end=end,
            )
            for period in canon
        }
        for period, fut in futs.items():
            result[period] = fut.result()
    return result


def _print_preview(pack: dict[str, Any], preview: int) -> None:
    items = pack.get("items") or []
    print(
        f"  {pack.get('period')}(interval={pack.get('interval')})  "
        f"count={pack.get('count')}  query={pack.get('query')}  "
        f"source={pack.get('source')}"
    )
    if not items:
        print("  (empty)")
        return
    shown = items[-preview:] if preview > 0 else items
    print(json.dumps(shown, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="从同花顺拉取 K 线")
    parser.add_argument("code", nargs="?", default="600519")
    parser.add_argument("--period", default="bars", help="周期，或 bars(日周月)")
    parser.add_argument("--adjust", default="qfq", help="none|qfq|hfq")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--beg", default="")
    parser.add_argument("--end", default="")
    args = parser.parse_args()

    key = (args.period or "bars").strip().lower()
    if key in ("bars", "dwm", "default", "all", "*"):
        chosen: tuple[str, ...] = DEFAULT_PERIODS
    else:
        chosen = (_period(key),)
    preview = args.limit if not args.beg else 5

    if len(chosen) == 1:
        pack = fetch_line(
            args.code, period=chosen[0], adjust=args.adjust,
            limit=args.limit, beg=args.beg, end=args.end,
        )
        print(f"{pack.get('security')} {pack.get('code')}  adjust={pack['adjust']}")
        _print_preview(pack, preview)
        return 0

    pack = fetch_lines(
        args.code, periods=chosen, adjust=args.adjust,
        limit=args.limit, beg=args.beg, end=args.end,
    )
    print(f"{pack.get('code')}  adjust={pack['adjust']}")
    for period in chosen:
        _print_preview(pack[period], preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
