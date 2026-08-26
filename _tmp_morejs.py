from pathlib import Path
import re, json, sys
sys.path.insert(0, str(Path("backend").resolve()))
from core.http import browser_get

js = Path("_tmp_wap_main.js").read_text(encoding="utf-8", errors="replace")
needles = ["remoteEntry", "stock-discussion", "community-scenes", "open/api", "lgt/", "content/list", "feed", "hexin"]
chunks = []
for key in needles:
    i = 0
    n = 0
    chunks.append(f"\n==== {key} {js.count(key)}")
    while n < 4:
        j = js.find(key, i)
        if j < 0:
            break
        chunks.append(js[max(0,j-80):j+200].replace("\n"," "))
        chunks.append("---")
        i = j + len(key)
        n += 1

# dump full index
hexin = "Hexin_Gphone/11.20.40 (Phone; Android 13; zh) Mozilla/5.0"
r = browser_get(
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/index",
    params={"code": "600519", "source": "stock", "marketId": "17"},
    headers={"User-Agent": hexin, "Referer": "https://t.10jqka.com.cn/m/guba/600519/", "Accept": "application/json"},
    timeout=20,
)
Path("_tmp_index.json").write_text(r.text or "", encoding="utf-8")
chunks.append("\nINDEX keys:")
try:
    p = json.loads(r.text)
    chunks.append(json.dumps(p, ensure_ascii=False)[:4000])
except Exception as e:
    chunks.append(str(e) + " " + (r.text or "")[:400])

Path("_tmp_js2.txt").write_text("\n".join(chunks), encoding="utf-8")
print("ok")
