import json
import sys
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.line.eastmoney_ticks import fetch_ticks

code = sys.argv[1] if len(sys.argv) > 1 else "002001"
name = sys.argv[2] if len(sys.argv) > 2 else "新和成"
threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 500_000

pack = fetch_ticks(code, pos=0)
items = pack.get("items") or []
day = date.today().isoformat()
big = []
for row in items:
    price = row.get("price") or 0
    vol = row.get("volume") or 0
    amt = price * vol * 100
    if amt >= threshold:
        side = "buy" if row.get("side") == 1 else "sell" if row.get("side") == 2 else "other"
        big.append(
            {
                "time": f"{day} {row['time']}",
                "code": code,
                "name": name,
                "price": price,
                "volume": vol * 100,
                "amount": round(amt, 2),
                "side": side,
                "side_label": row.get("side_label") or side,
            }
        )
buy = sum(x["amount"] for x in big if x["side"] == "buy")
sell = sum(x["amount"] for x in big if x["side"] == "sell")
out = {
    "code": code,
    "name": name,
    "date": day,
    "source": "eastmoney_ticks_filtered",
    "threshold": f"成交额>={threshold/10000:.0f}万元",
    "count": len(big),
    "summary": {
        "buy_amount": round(buy, 2),
        "sell_amount": round(sell, 2),
        "net_amount": round(buy - sell, 2),
        "buy_count": sum(1 for x in big if x["side"] == "buy"),
        "sell_count": sum(1 for x in big if x["side"] == "sell"),
    },
    "items": big,
}
print(json.dumps(out, ensure_ascii=False, indent=2))
