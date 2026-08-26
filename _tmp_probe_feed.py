"""Probe mobile LGT post list APIs with Hexin UA and exact SPA params."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path("backend").resolve()))
from core.http import browser_get

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "IHexin/11.50.41 (Royal Flush)"
)
headers = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://t.10jqka.com.cn/m/guba/600519/",
    "Origin": "https://t.10jqka.com.cn",
}

urls = []
for host in ["https://c.10jqka.com.cn", "https://t.10jqka.com.cn"]:
    for path in [
        "/lgt/post/open/api/forum/content/v1/recent",
        "/lgt/post/open/api/forum/content/v1/hot_feed",
    ]:
        for params in [
            {"code": "600519", "page": "1", "pageSize": "20"},
            {"code": "600519", "page": "1", "pageSize": "20", "marketId": "17"},
            {"code": "600519", "page": "1", "pageSize": "20", "pid": "0", "time": "0", "sort": "1"},
            {"fid": "114", "page": "1", "pageSize": "20"},
            {"code": "600519", "page": "1", "pageSize": "20", "sort": "time"},
        ]:
            from urllib.parse import urlencode
            urls.append(f"{host}{path}?{urlencode(params)}")

# also forum index for fid
urls.insert(0, "https://c.10jqka.com.cn/lgt/cache/open/api/forum/v2/index?code=600519&source=stock")

for url in urls:
    try:
        r = browser_get(url, timeout=15, headers=headers)
    except Exception as e:
        print(f"ERR {type(e).__name__} {url[:100]}")
        continue
    text = r.text or ""
    preview = text[:280].replace("\n", " ")
    print(f"{r.status_code:3} {len(text):7} {url}")
    print("   ", preview)
    # if looks like json with feed, dump keys
    if text.lstrip().startswith("{") and len(text) > 80:
        try:
            data = json.loads(text)
            print("    keys", list(data)[:12])
            inner = data.get("data") or data.get("result") or data
            if isinstance(inner, dict):
                print("    inner", list(inner)[:15])
                feed = inner.get("feed") or inner.get("list") or inner.get("posts")
                if isinstance(feed, list) and feed:
                    print("    feed0", list(feed[0]) if isinstance(feed[0], dict) else type(feed[0]))
                    Path("_tmp_feed_sample.json").write_text(
                        json.dumps(data, ensure_ascii=False, indent=2)[:8000],
                        encoding="utf-8",
                    )
                    print("    wrote _tmp_feed_sample.json")
        except Exception as e:
            print("    json err", e)
    print()
