from pathlib import Path
import re, sys
sys.path.insert(0, str(Path("backend").resolve()))
from core.http import browser_get

ua = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
r = browser_get(
    "https://t.10jqka.com.cn/m/guba/600519/",
    headers={"User-Agent": ua, "Referer": "https://t.10jqka.com.cn/m/"},
    timeout=25,
)
html = r.text or ""
Path("_tmp_wap.html").write_text(html, encoding="utf-8")
scripts = re.findall(r'src="([^"]+)"', html)
print("status", r.status_code, "len", len(html))
print("scripts:")
for s in scripts:
    print(" ", s)
print("api hints", re.findall(r'[/][a-zA-Z0-9_\-/]*(?:post|guba|comment|feed|circle)[^"\']{0,60}', html)[:40])
