from __future__ import annotations

import re

from core.http import browser_get, get_text

SINA_H = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}


def main() -> None:
    html = open("_tmp_dax.html", encoding="utf-8").read()
    # extract init config near papercode / KKE
    for key in ("papercode", "KKE.api", "global_index", "market", "symbol"):
        for m in re.finditer(key, html):
            ctx = html[max(0, m.start() - 30) : m.start() + 160]
            open("_tmp_dax_ctx.txt", "a", encoding="utf-8").write(ctx + "\n---\n")
    print("wrote contexts")

    # Download common.js mentioned on page
    for url in [
        "https://n.sinaimg.cn/finance/66ceb6d9/20241119/common.js?v2",
        "https://finance.sina.com.cn/other/src/sff.js",
    ]:
        try:
            t = get_text(url, headers=SINA_H, timeout=12) or ""
        except Exception as exc:  # noqa: BLE001
            print("FAIL", url, exc)
            continue
        print(url, "len", len(t))
        for pat in sorted(set(re.findall(r"https?://[^\s\"'`]+", t)))[:30]:
            if any(k in pat.lower() for k in ("kline", "api", "hq", "json", "day", "global")):
                print(" ", pat)
        for m in re.finditer(r".{0,50}(?:kline|KLine|getDay|datalen|znb_).{0,80}", t, re.I):
            open("_tmp_common_ctx.txt", "a", encoding="utf-8").write(m.group(0) + "\n---\n")

    # Try money.finance ML_DataList and similar
    symbols = ["znb_DAX", "znb_NKY", "znb_CAC", "znb_UKX", "znb_KOSPI", "znb_SX5E", "znb_SENSEX"]
    templates = [
        "https://money.finance.sina.com.cn/quotes_service/view/vML_DataList.php?asc=j&symbol={s}&num=100",
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={s}&scale=240&ma=no&datalen=100",
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/IO.X=/US_MinKService.getDailyK?symbol={s}",
        "https://finance.sina.com.cn/realstock/company/{s}/hisdata/klc_kl.js?d=2026",
        "https://finance.sina.com.cn/realstock/company/{s}/klc_kl.js",
        "https://hq.sinajs.cn/list=s_{s}",
    ]
    for s in symbols:
        for tmpl in templates:
            url = tmpl.format(s=s)
            try:
                t = get_text(url, headers=SINA_H, timeout=8) or ""
            except Exception as exc:  # noqa: BLE001
                print("FAIL", s, tmpl.split("/")[-1][:40], type(exc).__name__)
                continue
            preview = t[:100].replace("\n", " ")
            interesting = len(t) > 20 and "null" not in t[:30] and "ERROR" not in t and "404" not in t
            if interesting or "o\"" in t[:80] or "open" in t[:80] or t.startswith("["):
                print("HIT?", s, url[-55:], preview)
            else:
                print("miss", s, url[-40:], preview[:60])


if __name__ == "__main__":
    open("_tmp_dax_ctx.txt", "w", encoding="utf-8").write("")
    open("_tmp_common_ctx.txt", "w", encoding="utf-8").write("")
    main()
