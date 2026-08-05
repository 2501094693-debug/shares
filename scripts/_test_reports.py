import traceback
from datetime import datetime, timedelta
import json

print("PART 1: akshare")
try:
    import akshare as ak
    df = ak.stock_research_report_em(symbol="600519")
    print("=== ak.stock_research_report_em ===")
    print("columns:", list(df.columns))
    print("row_count:", len(df))
    print("head(2) records:")
    for i, rec in enumerate(df.head(2).to_dict("records")):
        print(f"--- row {i} ---")
        for k, v in rec.items():
            print(f"  {k!r}: {v!r}")
except Exception as e:
    print("EXCEPTION:", type(e).__name__, str(e))
    traceback.print_exc()

print("\nPART 2: eastmoney API")
begin = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
end = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
params = {
    "code": "600519",
    "beginTime": begin,
    "endTime": end,
    "pageSize": 50,
    "qType": 0,
    "pageNo": 1,
}
url = "https://reportapi.eastmoney.com/report/list"

def try_curl_cffi():
    from curl_cffi import requests as creq
    r = creq.get(url, params=params, impersonate="chrome", timeout=30)
    r.raise_for_status()
    return r.json()

def try_requests():
    import requests
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://data.eastmoney.com/",
    }
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()

data = None
for name, fn in [("curl_cffi", try_curl_cffi), ("requests", try_requests)]:
    try:
        data = fn()
        print(f"success via {name}")
        break
    except Exception as e:
        print(f"{name} failed:", type(e).__name__, str(e))
        traceback.print_exc()

if data is not None:
    if isinstance(data, dict):
        print("top-level keys:", list(data.keys()))
        for k in ("data", "result", "Data", "Result"):
            if k in data:
                inner = data[k]
                print(f"  [{k!r}] type:", type(inner).__name__)
                if isinstance(inner, dict):
                    print(f"  [{k!r}] keys:", list(inner.keys()))
                    for ik in ("data", "list", "items", "records"):
                        if ik in inner and isinstance(inner[ik], list) and inner[ik]:
                            print(f"  first item keys ({ik}):", list(inner[ik][0].keys()))
                            print("  first item sample:", json.dumps(inner[ik][0], ensure_ascii=False, default=str)[:2000])
                            break
                elif isinstance(inner, list) and inner:
                    print(f"  first item keys:", list(inner[0].keys()))
                    print("  first item sample:", json.dumps(inner[0], ensure_ascii=False, default=str)[:2000])
                break
    else:
        print("unexpected top-level type:", type(data))
