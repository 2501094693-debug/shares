"""Stooq daily CSV via curl_cffi session + POW verify."""
from __future__ import annotations

import hashlib
import re

from curl_cffi import requests as curl_requests

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def solve_pow(html: str) -> tuple[str, int] | None:
    m = re.search(r'const c="([^"]+)",d=(\d+),t="0"\.repeat\(d\)', html)
    if not m:
        return None
    c, d = m.group(1), int(m.group(2))
    prefix = "0" * d
    n = 0
    while n < 5_000_000:
        if hashlib.sha256(f"{c}{n}".encode()).hexdigest().startswith(prefix):
            return c, n
        n += 1
    return None


def fetch_csv(symbol: str, limit: int = 10) -> list[str]:
    sess = curl_requests.Session(impersonate="chrome")
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    r = sess.get(url, headers=UA, timeout=20)
    text = r.text
    if "Date," in text or text.startswith("Date"):
        return [ln for ln in text.splitlines() if ln and not ln.startswith("Date")][-limit:]
    solved = solve_pow(text)
    if not solved:
        print(symbol, "cannot solve", text[:100].replace("\n", " "))
        return []
    c, n = solved
    vr = sess.post(
        "https://stooq.com/__verify",
        data={"c": c, "n": str(n)},
        headers={
            **UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://stooq.com",
            "Referer": url,
        },
        timeout=20,
    )
    print(symbol, "verify", vr.status_code, vr.text[:40], "cookies", dict(sess.cookies))
    r2 = sess.get(url, headers=UA, timeout=20)
    text2 = r2.text
    if "Date" in text2:
        return [ln for ln in text2.splitlines() if ln and not ln.startswith("Date")][-limit:]
    print(symbol, "still blocked", text2[:120].replace("\n", " "))
    return []


if __name__ == "__main__":
    for s in ["^dax", "^nkx", "^ukx", "^cac", "^kospi", "^stx", "^sensex", "^hsi", "^dji"]:
        rows = fetch_csv(s, 3)
        print(s, "rows", len(rows), rows)
