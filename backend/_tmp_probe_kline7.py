"""Probe THS + sina globalindex page for overseas index daily klines."""
from __future__ import annotations

import re

from core.http import browser_get, get_text

THS_H = {"Referer": "https://q.10jqka.com.cn/", "User-Agent": "Mozilla/5.0"}
SINA_H = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}


def try_ths(code: str) -> None:
    url = f"https://d.10jqka.com.cn/v6/line/{code}/01/last.js"
    try:
        t = get_text(url, headers=THS_H, timeout=8) or ""
    except Exception as exc:  # noqa: BLE001
        print("ths FAIL", code, type(exc).__name__, str(exc)[:60])
        return
    # extract price count roughly
    m = re.search(r'"data":"([^"]+)"', t)
    n = len(m.group(1).split(";")) if m else 0
    print("ths HIT" if n else "ths empty", code, "n≈", n, t[:80].replace("\n", " "))


def scrape_sina_global() -> None:
    print("=== sina globalindex page ===")
    r = browser_get("https://finance.sina.com.cn/money/globalindex/", headers=SINA_H, timeout=15)
    text = r.text
    # any script src or api
    urls = sorted(set(re.findall(r"https?://[^\"'\s]+", text)))
    interesting = [
        u
        for u in urls
        if any(k in u.lower() for k in ("kline", "hq.", "api", "znb", "global", "json", "day"))
    ]
    for u in interesting[:40]:
        print("url", u)
    # znb symbols on page
    syms = sorted(set(re.findall(r"znb_[A-Z0-9]+", text)))
    print("znb", syms)
    ints = sorted(set(re.findall(r"int_[a-z0-9]+", text)))
    print("int", ints)


def scrape_ths_world() -> None:
    print("=== ths world pages ===")
    for url in [
        "https://q.10jqka.com.cn/global/",
        "https://stockpage.10jqka.com.cn/1A0001/",
        "https://q.10jqka.com.cn/qs/index_world.html",
    ]:
        try:
            r = browser_get(url, headers=THS_H, timeout=12)
        except Exception as exc:  # noqa: BLE001
            print(url, type(exc).__name__, exc)
            continue
        codes = sorted(set(re.findall(r"(?:line/|code[=:])([a-z0-9_]+)", r.text, re.I)))
        print(url, "status", r.status_code, "len", len(r.text), "sample codes", codes[:30])


if __name__ == "__main__":
    scrape_sina_global()
    print("=== THS code guesses ===")
    for code in [
        "hk_HSI",
        "us_DJI",
        "us_INX",
        "us_IXIC",
        "18_DAX",
        "88_DAX",
        "GI_DAX",
        "GI_N225",
        "world_N225",
        "zs_N225",
        "bk_DAX",
        "fe_DAX",
        "ff_DAX",
        "uk_FTSE",
        "uk_UKX",
        "jp_N225",
        "kr_KS11",
        "in_SENSEX",
        "eu_SX5E",
        "fr_FCHI",
        "de_GDAXI",
        "de_DAX",
        "48_1B0300",
    ]:
        try_ths(code)
    scrape_ths_world()
