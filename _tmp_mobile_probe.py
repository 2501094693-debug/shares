"""Probe Tonghuashun mobile community endpoints. Output UTF-8 file."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from core.http import browser_get, browser_post

OUT = Path("_tmp_mobile.txt")
lines: list[str] = []

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
HEXIN_UA = "Hexin_Gphone/11.20.40 (Phone; Android 13; zh) hxtheme/0 innerversion/G037.08.543.1.12"
CODE = "600519"


def dump(label: str, resp, n: int = 280) -> None:
    text = getattr(resp, "text", "") or ""
    status = getattr(resp, "status_code", "?")
    snippet = text.replace("\n", " ")[:n]
    lines.append(f"==== {label} status={status} len={len(text)}")
    lines.append(snippet)
    lines.append("")


def get(url, *, params=None, headers=None, ua=MOBILE_UA):
    hdrs = {"User-Agent": ua, **(headers or {})}
    return browser_get(url, params=params, headers=hdrs, timeout=20)


def post(url, *, data=None, headers=None, ua=MOBILE_UA):
    hdrs = {"User-Agent": ua, **(headers or {})}
    return browser_post(url, data=data, headers=hdrs, timeout=20)


# WAP pages
for url in [
    f"https://t.10jqka.com.cn/m/guba/{CODE}/",
    f"https://t.10jqka.com.cn/m/guba/{CODE}",
    f"https://eq.10jqka.com.cn/wap/guba/{CODE}.html",
    f"https://m.10jqka.com.cn/stockpage/{CODE}/",
    f"https://stockpage.10jqka.com.cn/{CODE}/",
]:
    try:
        dump(f"GET {url}", get(url, headers={"Referer": "https://m.10jqka.com.cn/"}))
    except Exception as exc:
        lines.append(f"==== GET {url} EXC {exc}\n")

# getPostList with mobile UA, no cookie
try:
    dump(
        "POST getPostList mobile",
        post(
            "https://t.10jqka.com.cn/newcircle/post/getPostList/",
            data={"type": "1", "fid": "2372", "first": "1", "page": "1"},
            headers={
                "Referer": f"https://t.10jqka.com.cn/guba/{CODE}/",
                "Origin": "https://t.10jqka.com.cn",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        ),
    )
except Exception as exc:
    lines.append(f"==== getPostList EXC {exc}\n")

# hexin UA getPostList
try:
    dump(
        "POST getPostList hexin",
        post(
            "https://t.10jqka.com.cn/newcircle/post/getPostList/",
            data={"type": "1", "fid": "2372", "first": "1", "code": CODE},
            headers={
                "Referer": f"https://t.10jqka.com.cn/m/guba/{CODE}/",
                "Origin": "https://t.10jqka.com.cn",
                "X-Requested-With": "com.hexin.plat.android",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            ua=HEXIN_UA,
        ),
    )
except Exception as exc:
    lines.append(f"==== hexin getPostList EXC {exc}\n")

candidates = [
    ("GET", "https://t.10jqka.com.cn/newcircle/post/getPostList/", {"code": CODE, "type": 1, "page": 1}),
    ("GET", "https://t.10jqka.com.cn/lgt/getPostList", {"code": CODE, "page": 1}),
    ("GET", "https://eq.10jqka.com.cn/openapi/comment/v1/getStockCommentList", {"code": CODE, "page": 1}),
    ("GET", "https://eq.10jqka.com.cn/openapi/stock/comment/list", {"code": CODE}),
    ("GET", "https://comment.10jqka.com.cn/getCommentList", {"code": CODE}),
    ("GET", "https://t.10jqka.com.cn/newcircle/group/getFeed/", {"code": CODE}),
    ("GET", "https://t.10jqka.com.cn/newcircle/group/getGroupFeed/", {"code": CODE, "fid": 2372}),
    ("GET", f"https://t.10jqka.com.cn/m/guba/{CODE}/getPostList", None),
    ("GET", "https://news.10jqka.com.cn/tapp/news/push/stock/", {"code": CODE}),
]

for method, url, params in candidates:
    try:
        dump(f"{method} {url} {params}", get(url, params=params, headers={"Referer": "https://t.10jqka.com.cn/", "X-Requested-With": "XMLHttpRequest"}, ua=HEXIN_UA))
    except Exception as exc:
        lines.append(f"==== {url} EXC {exc}\n")

OUT.write_text("\n".join(lines), encoding="utf-8")
print("wrote", OUT, "bytes", OUT.stat().st_size)
