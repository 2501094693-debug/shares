"""东财 ``/api/qt/stock/kline/get`` 全周期接入。

周期 ``klt``：
- 分钟：1 / 5 / 15 / 30 / 60 / 120
- 日及以上：101 日、102 周、103 月、104 季、105 半年、106 年

复权 ``fqt``：0 不复权、1 前复权、2 后复权。

两种查询（``beg`` 是否出现会改变 ``lmt`` 语义）：
- 最近 N 根：只传 ``end=20500101`` + ``lmt=N``，**不要传 beg**
- 日期区间：传 ``beg`` + ``end``；此时 ``lmt`` 经常被忽略

``secid`` 支持个股、指数、ETF、板块。历史 K 线以 ``push2his`` 为准。

    python company/line/eastmoney_kline.py 600519
    python company/line/eastmoney_kline.py 1.000001 --period day --limit 5
    python company/line/eastmoney_kline.py 90.BK0477 --period week
    python company/line/eastmoney_kline.py 600519 --period 5m --limit 10
    python company/line/eastmoney_kline.py 600519 --period quarter --beg 20200101
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

from core.codes import normalize_code, secid as _stock_secid
from core.fmt import to_float
from core.http import get_json

logger = logging.getLogger(__name__)

# 规范名 → klt。东财行情页能切到的 K 线都在这里。
PERIOD_KLT: dict[str, str] = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
    "120m": "120",
    "day": "101",
    "week": "102",
    "month": "103",
    "quarter": "104",
    "halfyear": "105",
    "year": "106",
}

MINUTE_PERIODS: tuple[str, ...] = ("1m", "5m", "15m", "30m", "60m", "120m")
BAR_PERIODS: tuple[str, ...] = ("day", "week", "month", "quarter", "halfyear", "year")
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
    "120": "120m",
    "120m": "120m",
    "2h": "120m",
    "101": "day",
    "day": "day",
    "d": "day",
    "daily": "day",
    "102": "week",
    "week": "week",
    "w": "week",
    "weekly": "week",
    "103": "month",
    "month": "month",
    "m": "month",
    "monthly": "month",
    "104": "quarter",
    "quarter": "quarter",
    "q": "quarter",
    "season": "quarter",
    "qtr": "quarter",
    "105": "halfyear",
    "halfyear": "halfyear",
    "half": "halfyear",
    "hy": "halfyear",
    "h": "halfyear",
    "semiannual": "halfyear",
    "106": "year",
    "year": "year",
    "y": "year",
    "yearly": "year",
    "annual": "year",
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

# 历史 K 只在 his 上稳定；delay / push2 对 kline/get 经常空数组
_HOSTS = (
    "https://push2his.eastmoney.com",
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
)

_HEADERS = {"Referer": "https://quote.eastmoney.com/"}
_UT = "fa5fd1943c7b386f172d6893dbfba10b"

# data 顶层元数据（返回时已换成具名键，不是 f1/f2）：
# f1 代码 code、f2 市场 market、f3 名称 name、f4 小数位 decimal、
# f5 K 线总数 dktotal、f6 前 K 收盘 preKPrice、f7 昨收 prePrice；f8–f13 其余元数据
_FIELDS1 = "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
# klines 各列 → _parse_row：日期,开,收,高,低,成交量(手),成交额(元),振幅(%),涨跌幅(%),涨跌额,换手率(%)
_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"

_END_OPEN = "20500101"
_MAX_LMT = 10000

_PREFIX_MARKET = {"SH": "1", "SZ": "0", "BJ": "0"}

# 6 位代码里现有 detect_market 覆盖不到的基金 / 指数
_SSE_HEADS = ("50", "51", "52", "56", "58", "60", "68")
_SZSE_HEADS = ("00", "15", "16", "18", "20", "30", "39")

_SECID_RE = re.compile(r"^\d+\.[A-Za-z0-9]+$")
_BK_RE = re.compile(r"^(?:90\.)?BK(\d{3,6})$", re.I)

_PREFIX_RE = re.compile(r"^(SH|SZ|BJ)(\d{6})$", re.I)
_SUFFIX_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$", re.I)


def _normalize_period(period: str) -> str:
    key = (period or "day").strip().lower()
    if key in _PERIOD_ALIASES:
        return _PERIOD_ALIASES[key]
    if key in PERIOD_KLT:
        return key
    raise ValueError(
        "period 须为 1m|5m|15m|30m|60m|120m|day|week|month|quarter|halfyear|year"
    )


def _normalize_adjust(adjust: str | int) -> int:
    key = str(adjust if adjust is not None else "qfq").strip().lower()
    if key not in _ADJUST_MAP:
        raise ValueError("adjust 须为 none|qfq|hfq（或 0|1|2）")
    return _ADJUST_MAP[key]


def _adjust_label(fqt: int) -> str:
    return {0: "none", 1: "qfq", 2: "hfq"}.get(fqt, "none")


def _normalize_date(value: str) -> str:
    text = (value or "").replace("-", "").replace("/", "").strip()
    if not text:
        return ""
    if text in ("0", "1"):
        return text
    if len(text) == 8 and text.isdigit():
        return text
    raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")


def resolve_secid(code: str) -> str:
    """把各种写法收成东财 ``secid``。

    已是 ``1.600519`` / ``0.000001`` / ``90.BK0477`` 则原样返回。
    ``SH000001`` 是上证指数，``000001`` / ``SZ000001`` 是平安银行。
    """
    raw = (code or "").strip()
    if not raw:
        return ""

    bk = _BK_RE.match(raw)
    if bk:
        return f"90.BK{bk.group(1).zfill(4)}"

    compact = raw.upper().replace(" ", "")
    prefixed = _PREFIX_RE.match(compact)
    if prefixed:
        return f"{_PREFIX_MARKET[prefixed.group(1)]}.{prefixed.group(2)}"
    suffixed = _SUFFIX_RE.match(compact)
    if suffixed:
        return f"{_PREFIX_MARKET[suffixed.group(2)]}.{suffixed.group(1)}"

    if _SECID_RE.match(raw):
        return raw

    digits = re.sub(r"[^0-9]", "", raw)
    if len(digits) == 6:
        if digits.startswith(_SSE_HEADS):
            return f"1.{digits}"
        if digits.startswith(_SZSE_HEADS):
            return f"0.{digits}"
        if digits.startswith(("8", "4", "92")):
            return f"0.{digits}"

    return _stock_secid(raw)

def _build_params(
    *,
    sid: str,
    klt: str,
    fqt: int,
    limit: int,
    beg: str,
    end: str,
) -> tuple[dict[str, str], str]:
    params = {
        "secid": sid,
        "fields1": _FIELDS1,
        "fields2": _FIELDS2,
        "klt": klt,
        "fqt": str(fqt),
        "ut": _UT,
    }

    finish = end or _END_OPEN
    params["end"] = finish

    if beg:
        params["beg"] = beg
        params["lmt"] = str(_MAX_LMT)
        return params, "range"

    params["lmt"] = str(limit)
    return params, "last"

def _parse_row(line: str) -> dict[str, Any] | None:
    """解析东财 klines 的一行 CSV。列不够或开收都缺则返回 None。

    字段顺序（``fields2=f51..f61``）：
    日期/时间, 开, 收, 高, 低, 成交量(手), 成交额(元), 振幅(%), 涨跌幅(%), 涨跌额, 换手率(%)
    """
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
        "volume": to_float(parts[5]) if len(parts) > 5 else None,  # 成交量（手）
        "amount": to_float(parts[6]) if len(parts) > 6 else None,  # 成交额（元）
    }
    if len(parts) > 7:
        item["amplitude"] = to_float(parts[7])  # 振幅 %：(最高-最低)/昨收×100
    if len(parts) > 8:
        item["pct_chg"] = to_float(parts[8])  # 涨跌幅 %
    if len(parts) > 9:
        item["change"] = to_float(parts[9])  # 涨跌额：收盘-昨收
    if len(parts) > 10:
        item["turnover"] = to_float(parts[10])  # 换手率 %
    return item

def fetch_line(
    code: str,
    *,
    period: str = "day",
    adjust: str | int = "qfq",
    limit: int = 320,
    beg: str = "",
    end: str = "",
) -> dict[str, Any]:
    """从东财拉一根周期的 K 线。

    period: 1m|5m|15m|30m|60m|120m|day|week|month|quarter|halfyear|year
            也接受 klt 数字，如 ``101``、``5``。
    adjust: none|qfq|hfq（或 0|1|2），默认前复权。
    不传 ``beg`` 时按最近 ``limit`` 根拉；传了 ``beg`` 则按日期区间，``limit`` 不用。
    ``limit<=0`` 表示尽量拉满（``lmt=10000``）。
    """
    sid = resolve_secid(code)
    if not sid:
        raise ValueError("无效股票代码")

    period = _normalize_period(period)
    klt = PERIOD_KLT[period]

    fqt = _normalize_adjust(adjust)

    cap = int(limit) if limit is not None else 320
    if cap <= 0:
        cap = _MAX_LMT
    cap = max(1, min(cap, _MAX_LMT))

    beg = _normalize_date(beg)
    end = _normalize_date(end)

    params, query = _build_params(
        sid=sid, klt=klt, fqt=fqt, limit=cap, beg=beg, end=end
    )

    # 先占位；某个 host 成功后再用 data 覆盖。全部失败则带着这些默认值返回。
    name = ""  # 证券简称
    market: int | None = None  # 市场：1 沪、0 深/北
    decimal: int | None = None  # 价格小数位
    dktotal: int | None = None  # 该周期历史 K 线总根数
    pre_k_price: float | None = None  # 前一根收盘 preKPrice
    pre_price: float | None = None  # 昨收 prePrice
    out_code = normalize_code(code) or sid  # 对外代码；接口有 code 时再覆盖
    items: list[dict[str, Any]] = []  # 解析后的 K 线
    last_exc: Exception | None = None  # 最后一个 host 的异常，K 线全空时再抛

    for host in _HOSTS:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/kline/get",
                params=params,
                headers=_HEADERS,
                timeout=12,
            )

            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                continue

            klines = data.get("klines") or []
            if not klines:
                continue

            parsed: list[dict[str, Any]] = []
            for line in klines:
                row = _parse_row(str(line))
                if row:
                    parsed.append(row)

            if not parsed:
                continue

            if query == "last" and len(parsed) > cap:
                parsed = parsed[-cap:]

            items = parsed

            name = str(data.get("name") or "").strip()
            out_code = str(data.get("code") or out_code).strip()
            market = data.get("market")
            decimal = data.get("decimal")
            dktotal = data.get("dktotal")
            pre_k_price = to_float(data.get("preKPrice"))
            pre_price = to_float(data.get("prePrice"))
            break
        except Exception as exc:
            last_exc = exc
            logger.info("eastmoney line skip %s %s %s: %s", sid, period, host, exc)
            continue

    if not items and last_exc:
        raise last_exc

    return {
        "code": out_code,
        "secid": sid,
        "name": name,
        "market": market,
        "decimal": decimal,
        "dktotal": dktotal,
        "pre_k_price": pre_k_price,
        "pre_price": pre_price,
        "period": period,
        "klt": klt,
        "adjust": _adjust_label(fqt),
        "query": query,
        "source": "eastmoney" if items else "",
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
    sid = resolve_secid(code)
    if not sid:
        raise ValueError("无效股票代码")

    chosen = tuple(periods) if periods else DEFAULT_PERIODS
    canon = [_normalize_period(p) for p in chosen]

    fqt = _normalize_adjust(adjust)

    result: dict[str, Any] = {
        "code": "",
        "secid": sid,
        "name": "",
        "adjust": _adjust_label(fqt),
        "source": "eastmoney",
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
        if pack.get("name"):
            result["name"] = pack["name"]
            result["code"] = pack.get("code") or result["code"]
            break

    if not result["code"]:
        result["code"] = normalize_code(code) or sid
    return result


def _print_preview(pack: dict[str, Any], preview: int) -> None:
    items = pack.get("items") or []
    print(
        f"  {pack.get('period')}(klt={pack.get('klt')})  "
        f"{pack.get('name') or ''}  count={pack.get('count')}  "
        f"query={pack.get('query')}  source={pack.get('source')}"
    )
    if not items:
        print("  (empty)")
        return
    shown = items[-preview:] if preview > 0 else items
    print(json.dumps(shown, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="从东财拉取 K 线（全周期）")
    parser.add_argument(
        "code",
        nargs="?",
        default="600519",
        help="代码或 secid，如 600519 / SH000001 / 1.000001 / 90.BK0477",
    )
    parser.add_argument(
        "--period",
        default="bars",
        help="周期，或 bars(日周月) / all(日到年) / minutes(全部分钟)",
    )
    parser.add_argument("--adjust", default="qfq", help="none|qfq|hfq，默认前复权")
    parser.add_argument("--limit", type=int, default=5, help="最近根数；与 --beg 互斥")
    parser.add_argument("--beg", default="", help="起始日 YYYYMMDD，传入则走日期区间")
    parser.add_argument("--end", default="", help="结束日 YYYYMMDD")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    key = (args.period or "bars").strip().lower()
    if key in ("bars", "dwm", "default"):
        chosen: tuple[str, ...] = DEFAULT_PERIODS
    elif key in ("all", "*", "bar-all"):
        chosen = BAR_PERIODS
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
            f"{pack.get('secid')} {pack.get('code')} {pack.get('name') or ''}  "
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
        f"{pack.get('secid')} {pack.get('code')} {pack.get('name') or ''}  "
        f"adjust={pack['adjust']}"
    )
    for period in chosen:
        _print_preview(pack[period], args.limit if not args.beg else 5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
