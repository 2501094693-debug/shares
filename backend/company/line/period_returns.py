"""用日 K 计算近 3 日到近 1 年涨跌。

先腾讯 ``fqkline``，失败或空数据再东财 ``kline/get``。默认前复权。

区间按交易日近似（不是自然日）：
- 近 3 / 5 / 10 / 20 / 60 日
- 近半年 ≈ 120 个交易日
- 近 1 年 ≈ 250 个交易日
另附今年以来（YTD）。

    python company/line/period_returns.py 600519
    python company/line/period_returns.py 000001 --adjust none
    python company/line/period_returns.py sh000001
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.fmt import pct_change, to_float
from company.line.eastmoney_kline import fetch_line as fetch_eastmoney_line
from company.line.tencent_kline import fetch_line as fetch_tencent_line

logger = logging.getLogger(__name__)

# 交易日偏移。20≈月、60≈季、120≈半年、250≈年。
PERIODS: tuple[tuple[str, int, str], ...] = (
    ("change_3d", 3, "近3日"),
    ("change_5d", 5, "近5日"),
    ("change_10d", 10, "近10日"),
    ("change_20d", 20, "近20日"),
    ("change_60d", 60, "近60日"),
    ("change_half_year", 120, "近半年"),
    ("change_1y", 250, "近1年"),
)

# 250 个交易日 + 基准那一根；腾讯日 K 上限约 640。
_DAY_LIMIT = 320


def _closes_from_items(items: list[dict[str, Any]]) -> tuple[list[float], list[str]]:
    closes: list[float] = []
    dates: list[str] = []
    for item in items:
        close = to_float(item.get("close"))
        if close is None:
            continue
        dates.append(str(item.get("time") or "")[:10])
        closes.append(close)
    return closes, dates


def _period_entry(
    *,
    key: str,
    label: str,
    days: int,
    last: float,
    last_time: str,
    base: float,
    base_time: str,
) -> dict[str, Any]:
    text = pct_change(last, base)
    pct = to_float(text.rstrip("%")) if text else None
    return {
        "key": key,
        "label": label,
        "days": days,
        "pct": pct,
        "text": text,
        "base_time": base_time,
        "base_close": base,
        "last_time": last_time,
        "last_close": last,
    }


def calc_period_returns(items: list[dict[str, Any]]) -> dict[str, Any]:
    """收盘价序列 → 各区间涨跌。根数不够的区间直接跳过。"""
    closes, dates = _closes_from_items(items)
    if len(closes) < 2:
        return {"changes": {}, "last_time": "", "last_close": None}

    last = closes[-1]
    last_time = dates[-1] if dates else ""
    changes: dict[str, Any] = {}

    for key, days, label in PERIODS:
        idx = -(days + 1)
        if len(closes) <= days:
            continue
        base = closes[idx]
        base_time = dates[idx] if len(dates) > days else ""
        changes[key] = _period_entry(
            key=key,
            label=label,
            days=days,
            last=last,
            last_time=last_time,
            base=base,
            base_time=base_time,
        )

    year = last_time[:4] if last_time else ""
    if year:
        ytd_base = None
        ytd_time = ""
        for day, close in zip(dates, closes):
            if day.startswith(year):
                ytd_base = close
                ytd_time = day
                break
        if ytd_base is not None:
            changes["change_ytd"] = _period_entry(
                key="change_ytd",
                label="今年以来",
                days=0,
                last=last,
                last_time=last_time,
                base=ytd_base,
                base_time=ytd_time,
            )

    return {"changes": changes, "last_time": last_time, "last_close": last}


def _fetch_one(
    fetch,
    code: str,
    *,
    adjust: str | int,
    source: str,
) -> dict[str, Any] | None:
    try:
        pack = fetch(code, period="day", adjust=adjust, limit=_DAY_LIMIT)
    except Exception as exc:  # noqa: BLE001
        logger.info("%s kline skip %s: %s", source, code, exc)
        return None
    items = pack.get("items") if isinstance(pack, dict) else None
    if not items:
        logger.info("%s kline empty %s", source, code)
        return None
    return pack if isinstance(pack, dict) else None


def fetch_daily_line(
    code: str,
    *,
    adjust: str | int = "qfq",
) -> dict[str, Any]:
    """日 K：腾讯优先，东财兜底。两边都失败返回空 ``items``。"""
    pack = _fetch_one(fetch_tencent_line, code, adjust=adjust, source="tencent")
    if pack:
        pack["source"] = pack.get("source") or "tencent"
        return pack
    pack = _fetch_one(fetch_eastmoney_line, code, adjust=adjust, source="eastmoney")
    if pack:
        pack["source"] = pack.get("source") or "eastmoney"
        return pack
    return {"code": code, "name": "", "adjust": str(adjust), "source": "", "items": []}


def fetch_period_returns(
    code: str,
    *,
    adjust: str | int = "qfq",
) -> dict[str, Any]:
    """近 3 日到近 1 年涨跌。腾讯日 K 优先，失败再东财。

    顶层带 ``change_3d`` 等格式化百分比，方便和盘口字段对齐；
    ``changes`` 里是带基准日 / 收盘价的明细。
    """
    pack = fetch_daily_line(code, adjust=adjust)
    items = pack.get("items") or []
    computed = calc_period_returns(items)
    changes = computed.get("changes") or {}

    out: dict[str, Any] = {
        "code": pack.get("code") or code,
        "symbol": pack.get("symbol") or pack.get("secid") or "",
        "name": pack.get("name") or "",
        "adjust": pack.get("adjust") or str(adjust),
        "source": pack.get("source") or "",
        "count": len(items),
        "last_time": computed.get("last_time") or "",
        "last_close": computed.get("last_close"),
        "changes": changes,
    }
    for key, entry in changes.items():
        text = entry.get("text") or ""
        if text:
            out[key] = text
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="近 3 日到近 1 年涨跌（腾讯优先，东财兜底）")
    parser.add_argument(
        "code",
        nargs="?",
        default="600519",
        help="代码，如 600519 / sh000001 / SZ000001",
    )
    parser.add_argument("--adjust", default="qfq", help="none|qfq|hfq，默认前复权")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    result = fetch_period_returns(args.code, adjust=args.adjust)
    print(
        f"{result.get('symbol') or result.get('code')} "
        f"{result.get('name') or ''}  "
        f"source={result.get('source') or '-'}  "
        f"adjust={result.get('adjust')}  "
        f"count={result.get('count')}  "
        f"last={result.get('last_time')} {result.get('last_close')}"
    )
    rows = []
    for key, _days, label in PERIODS:
        entry = (result.get("changes") or {}).get(key)
        if not entry:
            rows.append({"label": label, "text": ""})
            continue
        rows.append(
            {
                "label": entry.get("label") or label,
                "text": entry.get("text") or "",
                "base": f"{entry.get('base_time')} {entry.get('base_close')}",
            }
        )
    ytd = (result.get("changes") or {}).get("change_ytd")
    if ytd:
        rows.append(
            {
                "label": ytd.get("label") or "今年以来",
                "text": ytd.get("text") or "",
                "base": f"{ytd.get('base_time')} {ytd.get('base_close')}",
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0 if result.get("source") else 1


if __name__ == "__main__":
    raise SystemExit(main())
