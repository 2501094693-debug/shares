import json
import sys
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("603259_sorted.json")
data = json.loads(path.read_text(encoding="utf-8-sig"))
items = sorted(data.get("items") or [], key=lambda row: row["time"])
side_map = {"buy": "买盘", "sell": "卖盘", "other": "集合竞价"}
print(f"{'时间':<10} {'价格':>8} {'成交量':>12} {'成交额':>10} {'方向'}")
print("-" * 50)
for row in items:
    side = side_map.get(row.get("side"), row.get("side", ""))
    amt_wan = (row.get("amount") or 0) / 10000
    t = str(row.get("time", ""))[11:19]
    print(
        f"{t:<10} {row.get('price', 0):>8.2f} "
        f"{row.get('volume', 0):>12,.0f} {amt_wan:>9.1f}万 {side}"
    )
print("-" * 50)
print("合计", len(items), "笔")
