import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from core.http import browser_get

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 IHexin/11.50.41 (Royal Flush)"
hdrs = {"User-Agent": UA}

js_urls = [
    "https://s.thsi.cn/cd/guba/stock-discussion-remoteEntry_1.0.29.js",
    "https://s.thsi.cn/cd/mbweb-lgt-circle/circle-remoteEntry_1.0.6.js",
]
out = []
for url in js_urls:
    r = browser_get(url, headers=hdrs, timeout=30)
    text = r.text or ""
    name = url.rsplit("/", 1)[-1]
    Path("_tmp_" + name).write_text(text, encoding="utf-8", errors="replace")
    out.append(f"==== {url} {r.status_code} {len(text)}")
    apis = sorted(set(re.findall(r"['\"]([^'\"]*(?:10jqka|open/api|/lgt/|/post|/comment|/forum|/feed|/content)[^'\"]*)['\"]", text, flags=re.I)))
    out.append(f"apis {len(apis)}")
    out.extend("  " + a[:160] for a in apis[:80])
    # extra chunk files
    chunks = sorted(set(re.findall(r"['\"]([^'\"]+\.js)['\"]", text)))
    keep = [c for c in chunks if "thsi" in c or "guba" in c or "lgt" in c or "static" in c]
    out.append("chunks " + str(len(keep)))
    out.extend("  " + c for c in keep[:40])
    out.append("")

Path("_tmp_remote_apis.txt").write_text("\n".join(out), encoding="utf-8")
print("done", len(out))
