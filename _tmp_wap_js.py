from pathlib import Path
import re, sys
sys.path.insert(0, str(Path("backend").resolve()))
from core.http import browser_get

url = "https://s.thsi.cn/cd/community-scenes/static/js/main.ca4132d6.js"
r = browser_get(url, timeout=30)
js = r.text or ""
Path("_tmp_wap_main.js").write_text(js, encoding="utf-8", errors="replace")
print("len", len(js), "status", r.status_code)

paths = sorted(set(re.findall(r'["\'](/[a-zA-Z0-9_\-./?=]+)["\']', js)))
keys = ("post", "guba", "comment", "feed", "circle", "dongmi", "lgt", "api", "newcircle", "forum", "reply")
print("interesting paths:")
for p in paths:
    if any(k in p.lower() for k in keys):
        print(" ", p)

print("http urls:")
for u in sorted(set(re.findall(r'https?://[^"\'\s]{8,120}', js))):
    if any(k in u.lower() for k in keys + ("10jqka", "thsi", "eq.")):
        print(" ", u[:150])
