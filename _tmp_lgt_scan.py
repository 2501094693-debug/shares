import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from core.http import browser_get

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "IHexin/11.50.41 (Royal Flush)"
)
hdrs = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://t.10jqka.com.cn/m/guba/600519/",
}

paths = [
    "/lgt/cache/open/api/forum/v2/index?code=600519",
    "/lgt/cache/open/api/forum/v2/post?code=600519",
    "/lgt/cache/open/api/forum/v2/posts?code=600519",
    "/lgt/cache/open/api/forum/v2/list?code=600519",
    "/lgt/cache/open/api/forum/v2/feed?code=600519",
    "/lgt/cache/open/api/forum/v2/content?code=600519",
    "/lgt/cache/open/api/forum/v2/comment?code=600519",
    "/lgt/cache/open/api/post/v2/list?code=600519",
    "/lgt/cache/open/api/post/v2/list?fid=114",
    "/lgt/cache/open/api/content/v2/list?code=600519",
    "/lgt/cache/open/api/content/v2/list?fid=114",
    "/lgt/cache/open/api/content/list?code=600519",
    "/lgt/cache/open/api/feed/v2/list?code=600519",
    "/lgt/cache/open/api/feed/list?fid=114&code=600519",
    "/lgt/open/api/forum/v2/index?code=600519",
    "/lgt/open/api/post/list?fid=114",
    "/lgt/open/api/content/list?fid=114",
    "/lgt/open/api/content/v1/query?fid=114",
    "/lgt/open/api/content/v2/query?code=600519",
    "/lgt/open/api/content/v2/list?code=600519&fid=114",
    "/lgt/open/api/forum/v2/post/list?code=600519",
    "/lgt/open/api/forum/post/list?fid=114",
    "/open/api/forum/v2/index?code=600519",
    "/open/api/content/v2/list?code=600519",
]
hosts = ["https://c.10jqka.com.cn", "https://eq.10jqka.com.cn"]
lines = []
for host in hosts:
    for path in paths:
        url = host + path
        try:
            r = browser_get(url, headers=hdrs, timeout=12)
            text = (r.text or "").replace("\n", " ")[:180]
            if r.status_code == 404 and "Route Not Found" in (r.text or "") and len(r.text or "") < 80:
                continue
            if r.status_code == 404 and len(r.text or "") < 200:
                continue
            lines.append(f"{r.status_code} {len(r.text or '')} {url}\n  {text}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"EXC {url} {exc}")

Path("_tmp_lgt_scan.txt").write_text("\n".join(lines), encoding="utf-8")
print("hits", len(lines))
