"""用日 K 算近 3 日到近 1 年涨跌。

日 K 走 ``company.line.fetcher.fetch_kline``（腾讯优先，东财兜底）。
区间按交易日近似（不是自然日）。20≈月、60≈季、120≈半年、250≈年。

    python company/statistics/period_returns.py 600519
    python company/statistics/period_returns.py 000001 --adjust none
    python company/statistics/period_returns.py sh000001
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
from company.line.fetcher import fetch_kline

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


def fetch_daily_line(
    code: str,
    *,
    adjust: str | int = "qfq",
) -> dict[str, Any]:
    """日 K。走 ``fetch_kline``，带缓存和双源兜底。"""
    return fetch_kline(code, period="day", adjust=adjust, limit=_DAY_LIMIT)


def _closes(items: list[dict[str, Any]]) -> tuple[list[float], list[str]]:
    """抽出有效收盘价和对应日期；缺收盘的根丢掉。"""
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
    """一根区间涨跌：pct 是数字，text 是带 % 的字符串。"""
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
    """日 K 收盘价序列 → 各区间涨跌。根数不够的区间直接跳过。

    「近 N 日」用倒数第 N+1 根当基准（中间隔了 N 个交易日）。
    例如近 3 日：closes[-4] → closes[-1]。今年以来用当年第一根有效收盘。
    """
    closes, dates = _closes(items)
    if len(closes) < 2:
        return {"changes": {}, "last_time": "", "last_close": None}

    last = closes[-1]
    last_time = dates[-1] if dates else ""
    changes: dict[str, Any] = {}

    for key, days, label in PERIODS:
        if len(closes) <= days:
            continue
        idx = -(days + 1)
        changes[key] = _period_entry(
            key=key,
            label=label,
            days=days,
            last=last,
            last_time=last_time,
            base=closes[idx],
            base_time=dates[idx],
        )

    year = last_time[:4]
    if year:
        for day, close in zip(dates, closes):
            if day.startswith(year):
                changes["change_ytd"] = _period_entry(
                    key="change_ytd",
                    label="今年以来",
                    days=0,
                    last=last,
                    last_time=last_time,
                    base=close,
                    base_time=day,
                )
                break

    return {"changes": changes, "last_time": last_time, "last_close": last}


def fetch_period_returns(
    code: str,
    *,
    adjust: str | int = "qfq",
) -> dict[str, Any]:
    """近 3 日到近 1 年涨跌。日 K 走 ``fetch_kline``（腾讯优先，东财兜底）。

    顶层带 ``change_3d`` 等格式化百分比，方便和盘口字段对齐；
    ``changes`` 里是带基准日 / 收盘价的明细。
    """
    pack = fetch_daily_line(code, adjust=adjust)
    items = pack.get("items") or []
    computed = calc_period_returns(items)
    changes = computed.get("changes") or {}

    out: dict[str, Any] = {
        "code": pack.get("code") or code,
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
    parser.add_argument("code", nargs="?", default="600519", help="600519 / sh000001 / SZ000001")
    parser.add_argument("--adjust", default="qfq", help="none|qfq|hfq，默认前复权")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    result = fetch_period_returns(args.code, adjust=args.adjust)
    print(
        f"{result.get('code')} {result.get('name') or ''}  "
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
