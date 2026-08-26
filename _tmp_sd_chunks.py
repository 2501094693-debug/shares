import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from core.http import browser_get

hdrs = {"User-Agent": "Mozilla/5.0"}
base = "https://s.thsi.cn/cd/guba/"
files = [
    "static/js/stock-discussion-core.bb077c12.js",
    "static/js/stock-discussion-mf-entry.ca24cc33.js",
    "static/js/stock-discussion-components.4cd18623.js",
    "static/js/stock-discussion-bootstrap.f022db0e.js",
]
out = []
blob = ""
for rel in files:
    r = browser_get(base + rel, headers=hdrs, timeout=30)
    text = r.text or ""
    blob += "\n" + text
    Path("_tmp_" + rel.rsplit("/", 1)[-1]).write_text(text, encoding="utf-8", errors="replace")
    out.append(f"{rel} {r.status_code} {len(text)}")

apis = sorted(set(re.findall(r"['\"]([^'\"]{8,160})['\"]", blob)))
keep = [
    a
    for a in apis
    if any(
        k in a.lower()
        for k in (
            "10jqka",
            "open/api",
            "/lgt/",
            "forum",
            "post",
            "comment",
            "feed",
            "content",
            "guba",
            "sns",
            "getlist",
            "getpost",
        )
    )
]
out.append(f"keep {len(keep)}")
out.extend(keep)
Path("_tmp_sd_apis.txt").write_text("\n".join(out), encoding="utf-8")
print("keep", len(keep), "files", len(files))
