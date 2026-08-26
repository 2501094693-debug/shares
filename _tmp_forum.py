from pathlib import Path
import re, sys, json
sys.path.insert(0, str(Path("backend").resolve()))
from core.http import browser_get, browser_post

ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
hexin = "Hexin_Gphone/11.20.40 (Phone; Android 13; zh)"
out = []

def dump(label, resp, n=400):
    text = getattr(resp, "text", "") or ""
    out.append(f"==== {label} status={getattr(resp,'status_code','?')} len={len(text)}")
    out.append(text.replace("\n"," ")[:n])
    out.append("")

# forum v2
for url, params in [
    ("https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/index", {"code": "600519"}),
    ("https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/index", {"fid": "2372"}),
    ("https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/index", {"stock": "600519", "page": 1}),
    ("https://c.10jqka.com.cn/lgt/open/api/forum/v2/index", {"code": "600519"}),
    ("https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/post/list", {"code": "600519"}),
]:
    try:
        dump(f"GET {url} {params}", browser_get(url, params=params, headers={"User-Agent": hexin, "Referer": "https://t.10jqka.com.cn/m/guba/600519/"}, timeout=20))
    except Exception as e:
        out.append(f"==== {url} EXC {e}\n")

# remote entries
for url in [
    "https://s.thsi.cn/cd/guba/stock-discussion-remoteEntry.js",
    "https://s.thsi.cn/cd/guba/stock-discussion-remoteEntry",
    "https://s.thsi.cn/cd/mbweb-lgt-circle/circle-remoteEntry.js",
]:
    try:
        r = browser_get(url, headers={"User-Agent": ua}, timeout=20)
        text = r.text or ""
        out.append(f"==== JS {url} status={r.status_code} len={len(text)}")
        paths = sorted(set(re.findall(r'["\']((?:https?:)?//[^"\']+|/[a-zA-Z0-9_\-./?=]+)["\']', text)))
        for p in paths:
            if any(k in p.lower() for k in ("api", "post", "guba", "comment", "forum", "lgt", "feed", "circle", "open")):
                out.append("  PATH " + p[:180])
        out.append("")
        Path("_tmp_remote.js").write_text(text[:200000], encoding="utf-8", errors="replace")
    except Exception as e:
        out.append(f"==== {url} EXC {e}\n")

Path("_tmp_forum.txt").write_text("\n".join(out), encoding="utf-8")
print("wrote", len("\n".join(out)))
