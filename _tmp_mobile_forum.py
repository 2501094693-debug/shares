import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from core.http import browser_get

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "IHexin/11.50.41 (Royal Flush)"
)
hdrs = {"User-Agent": UA, "Accept": "*/*"}

urls = [
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/index",
    "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/index?code=600519",
    "https://c.10jqka.com.cn/lgt/open/api/forum/v2/index?code=600519",
    "https://s.thsi.cn/cd/guba/stock-discussion-remoteEntry.js",
    "https://s.thsi.cn/cd/mbweb-lgt-circle/circle-remoteEntry.js",
]

out = []
for url in urls:
    try:
        r = browser_get(url, headers=hdrs, timeout=25)
        text = r.text or ""
        out.append(f"==== {url} status={r.status_code} len={len(text)}")
        out.append(text[:500].replace("\n", " "))
        if url.endswith(".js"):
            Path("_tmp_" + url.rsplit("/", 1)[-1]).write_text(text, encoding="utf-8", errors="replace")
            apis = sorted(set(re.findall(r"['\"](/[^'\"]{6,100}|https?://[^'\"]{10,120})['\"]", text)))
            keep = [
                a
                for a in apis
                if any(k in a.lower() for k in ("api", "post", "comment", "guba", "lgt", "forum", "feed", "circle", "10jqka"))
            ]
            out.append("APIS " + str(len(keep)))
            out.extend("  " + a for a in keep[:60])
    except Exception as exc:  # noqa: BLE001
        out.append(f"==== {url} EXC {exc}")
    out.append("")

Path("_tmp_mobile_probe2.txt").write_text("\n".join(out), encoding="utf-8")
print("wrote", len("\n".join(out)))
