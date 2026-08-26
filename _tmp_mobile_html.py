from pathlib import Path
import re, sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from core.http import browser_get

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
    "Mobile/15E148 Safari/604.1"
)
hdrs = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}
r = browser_get("https://t.10jqka.com.cn/m/guba/600519/", headers=hdrs, timeout=25)
html = r.text or ""
Path("_tmp_m_guba.html").write_text(html, encoding="utf-8")
print("status", r.status_code, "len", len(html))
scripts = re.findall(r'src="([^"]+\.js[^"]*)"', html)
print("scripts", len(scripts))
for s in scripts:
    print(s)
# also inline
for m in re.findall(r'<script[^>]*>([^<]{20,400})</script>', html):
    print("INLINE", m[:200].replace("\n"," "))
