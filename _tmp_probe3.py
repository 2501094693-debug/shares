from pathlib import Path
import re, sys
sys.path.insert(0, str(Path("backend").resolve()))
from core.http import browser_get

js = Path("_tmp_wap_main.js").read_text(encoding="utf-8", errors="replace")
# find tt= function near productionVersion
i = js.find("productionVersion")
print("around tt", js[max(0,i-500):i+200][:800])

hexin = "Hexin_Gphone/11.20.40 (Phone; Android 13; zh)"
hdrs = {"User-Agent": hexin, "Referer": "https://t.10jqka.com.cn/m/guba/600519/", "Accept": "application/json"}

urls = [
    "https://s.thsi.cn/cd/guba/stock-discussion-remoteEntry.js?v=1.0.29",
    "https://s.thsi.cn/cd/guba/stock-discussion-remoteEntry?v=1.0.29",
    "https://s.thsi.cn/cd/guba/1.0.29/stock-discussion-remoteEntry.js",
    "https://s.thsi.cn/cd/guba/stock-discussion-remoteEntry.1.0.29.js",
    "https://m.10jqka.com.cn/cd/guba/stock-discussion-remoteEntry.js",
]
lines = []
for u in urls:
    try:
        r = browser_get(u, headers={"User-Agent": hexin}, timeout=15)
        lines.append(f"{r.status_code} {len(r.text or '')} {u}")
        if r.status_code == 200 and len(r.text or "") > 500:
            Path("_tmp_disc.js").write_text(r.text, encoding="utf-8", errors="replace")
            lines.append("SAVED " + u)
    except Exception as e:
        lines.append(f"EXC {u} {e}")

# probe list APIs with fid=114
cands = [
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/feed",
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/feeds",
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/content",
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/contents",
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/post",
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/posts",
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/list",
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/comment",
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/comments",
    "https://c.10jqka.com.cn/lgt/cache/open/api/content/v2/list",
    "https://c.10jqka.com.cn/lgt/cache/open/api/content/v1/list",
    "https://c.10jqka.com.cn/lgt/open/api/content/v1/list",
    "https://c.10jqka.com.cn/lgt/open/api/forum/v2/feed",
    "https://c.10jqka.com.cn/sns/open/api/content/list",
    "https://c.10jqka.com.cn/lgt/cache/open/api/feed/v1/list",
]
params_sets = [
    {"fid": 114, "code": "600519", "source": "stock"},
    {"fid": 114, "page": 1, "limit": 20},
]
for url in cands:
    try:
        r = browser_get(url, params={"fid": 114, "code": "600519", "source": "stock", "page": 1}, headers=hdrs, timeout=12)
        text = (r.text or "")[:180].replace("\n"," ")
        lines.append(f"{r.status_code} {len(r.text or '')} {url} :: {text}")
    except Exception as e:
        lines.append(f"EXC {url} {e}")

Path("_tmp_probe3.txt").write_text("\n".join(lines), encoding="utf-8")
print("done", len(lines))
