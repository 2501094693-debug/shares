import re
import sys
import time

import requests

sys.path.insert(0, ".")
from core.http import browser_get

sess = requests.Session()
sess.trust_env = False
headers = {
    "x-app-id": "rU6QIu7JHe2gOUeR",
    "x-version": "1.0.0",
    "Origin": "https://datacenter.jin10.com",
    "Referer": "https://datacenter.jin10.com/",
}

base = "https://datacenter-api.jin10.com/reports/list_v2"
for aid in range(1, 150):
    params = {
        "max_date": "",
        "category": "ec",
        "attr_id": str(aid),
        "_": str(int(time.time() * 1000)),
    }
    try:
        r = sess.get(base, params=params, headers=headers, timeout=5)
        vals = r.json().get("data", {}).get("values", [])
        if not vals:
            continue
        v = vals[0][1]
        if v is None:
            continue
        fv = float(v)
        if 2.5 <= fv <= 4.5:
            print(f"aid={aid} n={len(vals)} latest={vals[0]} oldest={vals[-1]}")
    except Exception:
        pass
