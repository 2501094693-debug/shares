"""调试：直接请求东方财富新闻搜索 JSONP，检查接口是否可用。

用法（在 backend 目录下）::

    python -m news.scripts.run_eastmoney_news

只打印状态、命中数、本页日期范围，方便对照 agent 里的解析逻辑。
"""

from __future__ import annotations

import json
import sys

KEYWORD = "600719"

INNER_PARAM = {
    "uid": "",
    "keyword": KEYWORD,
    "type": ["cmsArticleWebOld"],
    "client": "web",
    "clientType": "web",
    "clientVersion": "curr",
    "param": {
        "cmsArticleWebOld": {
            "searchScope": "default",
            "sort": "default",
            "pageIndex": 1,
            "pageSize": 100,
            "preTag": "<em>",
            "postTag": "</em>",
        }
    },
}

URL = "https://search-api-web.eastmoney.com/search/jsonp"
PARAMS = {
    "cb": "jQuery_cb",
    "param": json.dumps(INNER_PARAM, ensure_ascii=False),
    "_": "1764599530176",
}
HEADERS = {
    "referer": f"https://so.eastmoney.com/news/s?keyword={KEYWORD}",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
}


def parse_jsonp(text: str) -> dict:
    """从 callback({...}) 中抽出 JSON 对象。"""
    start = text.find("(")
    end = text.rfind(")")
    return json.loads(text[start + 1 : end])


def find_key(obj, key: str, path: str = "") -> None:
    """递归打印某个字段出现的位置（用于排查 hitsTotal 等）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k == key:
                print("FOUND", p, v)
            find_key(v, key, p)
    elif isinstance(obj, list) and obj and len(obj) < 3:
        for i, item in enumerate(obj):
            find_key(item, key, f"{path}[{i}]")


def main() -> int:
    try:
        from curl_cffi import requests as req

        print("HTTP_LIB curl_cffi")
        resp = req.get(URL, params=PARAMS, headers=HEADERS, impersonate="chrome")
    except ImportError:
        import requests as req

        print("HTTP_LIB requests")
        resp = req.get(URL, params=PARAMS, headers=HEADERS)

    print("STATUS", resp.status_code)
    print("RAW_PREFIX", resp.text[:200])

    data = parse_jsonp(resp.text)
    print("TOP_KEYS", list(data.keys()))

    result = data.get("result") or {}
    print("RESULT_KEYS", list(result.keys()) if isinstance(result, dict) else type(result))
    find_key(data, "hitsTotal")

    cms = result.get("cmsArticleWebOld") if isinstance(result, dict) else None
    if isinstance(cms, list) and cms:
        dates = [str(x.get("date", x)) for x in cms if isinstance(x, dict)]
        print("LIST_LEN", len(cms))
        if dates:
            print("FIRST_DATE", dates[0])
            print("LAST_DATE", dates[-1])
    elif isinstance(cms, dict):
        print("CMS_DICT_KEYS", list(cms.keys()))
        items = cms.get("list") or cms.get("data") or []
        if items:
            dates = [str(x.get("date")) for x in items if isinstance(x, dict)]
            print("LIST_LEN", len(items))
            print("FIRST_DATE", dates[0] if dates else None)
            print("LAST_DATE", dates[-1] if dates else None)
    else:
        print("CMS_TYPE", type(cms))

    return 0


if __name__ == "__main__":
    sys.exit(main())
