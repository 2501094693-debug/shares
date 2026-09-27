from __future__ import annotations

import re

from core.http import browser_get, get_json, get_text

TX_H = {"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"}
SINA_H = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}


def main() -> None:
    # 1) Tencent world index pages
    for url in [
        "https://stockapp.finance.qq.com/mstats/?mod=all&id=gwjj",
        "https://finance.qq.com/stock/globalindex.htm",
        "https://gu.qq.com/usDAX.oq",
    ]:
        try:
            r = browser_get(url, headers=TX_H, timeout=12)
            codes = sorted(set(re.findall(r"(?:uk|ft|ge|gm|de|fr|jp|kr|in|eu|ff|zs)[A-Z0-9]{2,10}", r.text)))
            print(url[-40:], r.status_code, "codes", codes[:40], "len", len(r.text))
        except Exception as exc:  # noqa: BLE001
            print(url, type(exc).__name__, exc)

    # 2) qq search API
    for q in ["DAX30", "日经225指数", "CAC40", "KOSPI指数", "斯托克50", "SENSEX", "富时100"]:
        try:
            t = get_text(f"https://smartbox.gtimg.cn/s3/?v=2&q={q}&t=all", headers=TX_H, timeout=6) or ""
        except Exception as exc:  # noqa: BLE001
            print("search", q, exc)
            continue
        open("_tmp_tx_search.txt", "a", encoding="utf-8").write(q + " => " + t + "\n")
        print("search", q, t[:180])

    # 3) sina hq.js
    try:
        t = get_text("https://n.sinaimg.cn/finance/sff/hq.js?ver=1.981", headers=SINA_H, timeout=12) or ""
        print("hq.js len", len(t))
        for u in sorted(set(re.findall(r"https?://[^\s\"'`]+", t)))[:40]:
            print(" hq url", u)
        for m in re.finditer(r".{0,40}(?:kline|KLine|dayK|getDay|global).{0,100}", t, re.I):
            open("_tmp_hqjs_ctx.txt", "a", encoding="utf-8").write(m.group(0) + "\n---\n")
    except Exception as exc:  # noqa: BLE001
        print("hq.js", exc)

    # 4) Try ifzq with market prefix from qq stockapp
    url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    for sym in [
        "gwDAX",
        "gwN225",
        "gwCAC",
        "gwUKX",
        "gwKS11",
        "gwSX5E",
        "gwSENSEX",
        "jj_DAX",
        "jjDAX",
        "hgDAX",
        "qzDAX",
        "qz_DAX",
        "ptDAX",
        "giDAX",
        "gi_DAX",
        "GI_DAX",
    ]:
        try:
            payload = get_json(url, params={"param": f"{sym},day,,,3,"}, headers=TX_H, timeout=5) or {}
        except Exception:
            continue
        block = ((payload.get("data") or {}).get(sym) or {})
        rows = block.get("day") or block.get("qfqday") or []
        if rows:
            print("HIT", sym, rows[-1][:3])


if __name__ == "__main__":
    open("_tmp_tx_search.txt", "w", encoding="utf-8").write("")
    open("_tmp_hqjs_ctx.txt", "w", encoding="utf-8").write("")
    main()
