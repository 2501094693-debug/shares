from pathlib import Path
import re, sys
sys.path.insert(0, str(Path("backend").resolve()))
from core.http import browser_get

js = Path("_tmp_wap_main.js").read_text(encoding="utf-8", errors="replace")
# also fetch html for chunk names
html = Path("_tmp_wap.html").read_text(encoding="utf-8", errors="replace")
print("html chunks", re.findall(r'static/js/[^"\']+', html)[:20])
print("html css", re.findall(r'static/css/[^"\']+', html)[:20])

for key in ["forum/v2", "open/api", "content_list", "getPost", "post/list", "lgt/", "comment", "fid", "c.10jqka"]:
    print(f"\n==== {key} count={js.lower().count(key.lower())}")
    i = 0
    n = 0
    while n < 2:
        j = js.lower().find(key.lower(), i)
        if j < 0:
            break
        print(js[max(0,j-120):j+220].replace("\n"," ")[:400])
        print("---")
        i = j + len(key)
        n += 1
