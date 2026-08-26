import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from core.http import browser_get

url = "https://s.thsi.cn/cd/community-scenes/static/js/main.ca4132d6.js"
r = browser_get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=40)
t = r.text or ""
Path("_tmp_mobile_main.js").write_text(t, encoding="utf-8", errors="replace")
print("len", len(t))
paths = sorted(set(re.findall(r"['\"](/newcircle/[^'\"]+)['\"]", t)))
print("newcircle", len(paths))
for p in paths:
    print(p)
print("---keys---")
for key in (
    "getPostList",
    "getComment",
    "guba",
    "dongmi",
    "getFeed",
    "community",
    "openapi",
    "eq.10jqka",
    "comment",
    "getPost",
    "stockCode",
    "lgt",
    "snsHttp",
    "getList",
):
    print(key, t.count(key))
print("---http urls---")
urls = sorted(set(re.findall(r"https?://[^\"'\\s]{10,120}", t)))
for u in urls:
    if any(k in u.lower() for k in ("10jqka", "thsi", "comment", "guba", "circle", "sns")):
        print(u)
