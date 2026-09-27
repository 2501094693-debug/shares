from __future__ import annotations

import re

from core.http import get_text

t = (
    get_text(
        "https://finance.sina.com.cn/sinafinancesdk/js/plugins/sinaTKChart.js",
        headers={"Referer": "https://finance.sina.com.cn"},
        timeout=15,
    )
    or ""
)
open("_tmp_tkchart.js", "w", encoding="utf-8").write(t)
print("len", len(t))

urls = sorted(set(re.findall(r"https?://[^\s\"'`\\]+", t)))
print("urls", len(urls))
for u in urls:
    print(u)

# keyword contexts
for key in ("kline", "KLine", "getDay", "datalen", "scale", "hq_str", "cn_market", "jsonp", "day"):
    idx = 0
    n = 0
    while n < 5:
        i = t.lower().find(key.lower(), idx)
        if i < 0:
            break
        ctx = t[max(0, i - 60) : i + 120].replace("\n", " ")
        print(f"CTX[{key}]", ctx)
        idx = i + len(key)
        n += 1
