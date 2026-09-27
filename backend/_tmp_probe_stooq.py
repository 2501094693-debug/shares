"""Solve Stooq browser proof-of-work and fetch daily CSV."""
from __future__ import annotations

import hashlib
import re

from core.http import browser_get

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def solve_pow(html: str) -> tuple[str, int] | None:
    m = re.search(
        r'const c="([^"]+)",d=(\d+),t="0"\.repeat\(d\)',
        html,
    )
    if not m:
        return None
    c = m.group(1)
    d = int(m.group(2))
    prefix = "0" * d
    n = 0
    while True:
        digest = hashlib.sha256(f"{c}{n}".encode()).hexdigest()
        if digest.startswith(prefix):
            return c, n
        n += 1
        if n > 5_000_000:
            return None


def fetch_stooq(symbol: str) -> None:
    url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
    r = browser_get(url, headers=UA, timeout=20)
    text = r.text
    if "Date" in text and "Open" in text:
        lines = [ln for ln in text.splitlines() if ln and not ln.startswith("Date")]
        print(symbol, "direct", len(lines), lines[-1] if lines else None)
        return
    solved = solve_pow(text)
    if not solved:
        print(symbol, "no pow / blocked", text[:80].replace("\n", " "))
        return
    c, n = solved
    print(symbol, "pow solved", c[:12], n)
    # verify
    verify = browser_get(
        "https://stooq.com/__verify",
        # browser_get may not support POST — try with get_text/post
        headers=UA,
        timeout=15,
    )
    print("verify get?", verify.status_code, verify.text[:60])


if __name__ == "__main__":
    # First inspect if we have POST helper
    from core import http as httpmod

    print("http helpers", [x for x in dir(httpmod) if not x.startswith("_")])
    for s in ["^dax", "^nkx", "^ukx"]:
        fetch_stooq(s)
