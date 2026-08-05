import json, sys
sys.path.insert(0, r"C:\Users\Administrator\Desktop\test\backend")
import akshare as ak
from news.agent import _fetch_notices, _is_important_notice

out = {}
for code in ("600519", "600719"):
    df = ak.stock_individual_notice_report(security=code, begin_date="20240803", end_date="20260803")
    out[code] = {
        "rows": len(df),
        "min_date": str(df["公告日期"].min()),
        "max_date": str(df["公告日期"].max()),
        "type_counts_top15": df["公告类型"].value_counts().head(15).to_dict(),
    }
items = _fetch_notices("600519")
important = [x for x in items if _is_important_notice(x)]
out["news_agent_600519"] = {
    "fetch_len": len(items),
    "important_len": len(important),
    "dropped": len(items)-len(important),
}
# dropped types
from collections import Counter
dropped_types = Counter(x.get("summary") for x in items if not _is_important_notice(x))
kept_types = Counter(x.get("summary") for x in important)
out["dropped_type_top10"] = dict(dropped_types.most_common(10))
out["kept_type_top10"] = dict(kept_types.most_common(10))
print(json.dumps(out, ensure_ascii=False, indent=2))
