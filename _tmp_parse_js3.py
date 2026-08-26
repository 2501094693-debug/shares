import re
from pathlib import Path

t = Path("_tmp_mobile_main.js").read_text(encoding="utf-8", errors="replace")
html = Path("_tmp_m_guba.html").read_text(encoding="utf-8", errors="replace")

print("=== lgt/forum/open/api occurrences ===")
for key in ("lgt/cache", "open/api", "forum/v2", "c.10jqka", "stock-discussion", "remoteEntry", "content_list", "getPost"):
    idxs = [i for i in range(len(t)) if t.startswith(key, i)]
    print(key, "js", t.count(key), "html", html.count(key))
    i = t.find(key)
    if i >= 0:
        print(" ", t[max(0, i - 80) : i + 160].replace("\n", " "))

print("=== html remote ===")
for m in re.findall(r"[a-zA-Z0-9./_-]*remoteEntry[a-zA-Z0-9./_-]*", html):
    print(m)
for m in re.findall(r"s\.thsi\.cn/cd/[a-zA-Z0-9_./-]+", html + t):
    print("cd", m)
