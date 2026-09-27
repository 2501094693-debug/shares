"""Probe Sina / Yahoo / Tencent for remaining overseas indices."""
from __future__ import annotations

import json
import re

from core.http import get_json, get_text, browser_get

SINA_H = {"Referer": "https://finance.sina.com.cn"}
TX_H = {"Referer": "https://gu.qq.com/"}


def extract_jsonp(text: str):
    m = re.search(r"=\((.*)\)\s*;?\s*$", text, re.S)
    if not m:
        return None
    raw = m.group(1)
    if raw in ("null", ""):
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def try_sina_us(symbol: str, limit: int = 5) -> int:
    url = (
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/"
        f"var%20_X=/US_MinKService.getDailyK?symbol={symbol}"
    )
    try:
        text = get_text(url, headers=SINA_H, timeout=8) or ""
    except Exception as exc:
        print(f"FAIL sina {symbol}: {exc}")
        return 0
    data = extract_jsonp(text)
    if isinstance(data, list) and data:
        print(f"HIT sina {symbol}: {len(data)} last={data[-1]}")
        return len(data)
    # also try plain json endpoint
    url2 = f"https://stock.finance.sina.com.cn/usstock/api/json.php/US_MinKService.getDailyK?symbol={symbol}"
    try:
        text2 = get_text(url2, headers=SINA_H, timeout=8) or ""
        rows = json.loads(text2) if text2.startswith("[") else None
        if isinstance(rows, list) and rows:
            print(f"HIT sina-json {symbol}: {len(rows)} last={rows[-1]}")
            return len(rows)
    except Exception as exc:
        print(f"miss sina-json {symbol}: {exc}")
    print(f"miss sina {symbol}")
    return 0


def try_yahoo(symbol: str) -> int:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "3mo"}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        payload = get_json(url, params=params, headers=headers, timeout=8) or {}
    except Exception as exc:
        print(f"FAIL yahoo {symbol}: {type(exc).__name__}")
        return 0
    result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
    ts = result.get("timestamp") or []
    print(f"{'HIT' if ts else 'miss'} yahoo {symbol}: {len(ts)}")
    return len(ts)


def try_tx_quote(*codes: str) -> None:
    url = "https://qt.gtimg.cn/q=" + ",".join(codes)
    try:
        text = get_text(url, headers=TX_H, timeout=6) or ""
    except Exception as exc:
        print(f"FAIL qt: {exc}")
        return
    for line in text.split(";"):
        line = line.strip()
        if not line:
            continue
        # v_xxx="name~..."
        m = re.match(r'v_([^=]+)="([^"]*)"', line)
        if not m:
            continue
        code, body = m.group(1), m.group(2)
        parts = body.split("~")
        name = parts[1] if len(parts) > 1 else ""
        price = parts[3] if len(parts) > 3 else ""
        if name or price:
            print(f"qt {code}: name={name!r} price={price}")


# Sina symbols for global indices (guesses)
sina_syms = [
    ".dji", ".inx", ".ixic", ".ndx",
    ".ftse", ".dax", ".cac", ".n225", ".nikkei", ".hsi",
    ".ks11", ".kospi", ".sensex", ".sx5e", ".stoxx50",
    "ftse", "dax", "cac40", "n225", "nikkei225", "hsi",
    "ks11", "sensex", "sx5e", "eurostoxx50",
    # some pages use these
    "UKX", "DAX", "CAC", "NKY", "KOSPI", "SENSEX", "SX5E",
]

print("=== Sina US_MinKService ===")
for s in sina_syms:
    try_sina_us(s, 3)

print("\n=== Yahoo ===")
for s in ["^DJI", "^GSPC", "^IXIC", "^FTSE", "^GDAXI", "^FCHI", "^N225", "^KS11", "^BSESN", "^STOXX50E", "^HSI"]:
    try_yahoo(s)

print("\n=== Tencent qt probe ===")
try_tx_quote(
    "usDJI", "ukUKX", "deDAX", "frCAC", "jpN225", "krKS11", "hkHSI",
    "ff_DAX", "ff_CAC", "ff_N225", "ff_FTSE", "ff_HSI",
    "gz_DAX", "r_DAX", "s_DAX",
)
