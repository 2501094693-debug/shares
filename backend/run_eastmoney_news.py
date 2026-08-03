import json
import sys

inner_param = {
    "uid": "",
    "keyword": "600719",
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

url = "https://search-api-web.eastmoney.com/search/jsonp"
params = {
    "cb": "jQuery_cb",
    "param": json.dumps(inner_param, ensure_ascii=False),
    "_": "1764599530176",
}
headers = {
    "referer": "https://so.eastmoney.com/news/s?keyword=600719",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
}

def parse_jsonp(text):
    start = text.find("(")
    end = text.rfind(")")
    return json.loads(text[start + 1 : end])

try:
    from curl_cffi import requests as req
    print("HTTP_LIB curl_cffi")
    r = req.get(url, params=params, headers=headers, impersonate="chrome")
except ImportError:
    import requests as req
    print("HTTP_LIB requests")
    r = req.get(url, params=params, headers=headers)

print("STATUS", r.status_code)
print("RAW_PREFIX", r.text[:200])
data = parse_jsonp(r.text)
print("TOP_KEYS", list(data.keys()))
result = data.get("result") or {}
print("RESULT_KEYS", list(result.keys()) if isinstance(result, dict) else type(result))

# print hitsTotal wherever it appears
def find_key(obj, key, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k == key:
                print("FOUND", p, v)
            find_key(v, key, p)
    elif isinstance(obj, list) and obj and len(obj) < 3:
        for i, item in enumerate(obj):
            find_key(item, key, f"{path}[{i}]")

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
