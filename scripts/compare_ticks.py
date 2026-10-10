"""三源秒级逐笔对比：同花顺 / 东财 / 腾讯，600519 上一交易日。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

CODE = "600519"
DAY = "2026-10-09"  # 上一交易日（周五）

results = {}


def summarize(name, items):
    prices = [r["price"] for r in items if r.get("price") is not None]
    vols = [r.get("volume") or 0 for r in items]
    times = [str(r.get("time") or "") for r in items]
    print(f"--- {name}: count={len(items)}")
    if not items:
        print("    (empty)")
        return
    print(f"    time range: {times[0]} .. {times[-1]}")
    print(f"    price: min={min(prices):.2f} max={max(prices):.2f} "
          f"first={prices[0]:.2f} last={prices[-1]:.2f}")
    print(f"    total volume(股)={sum(vols):.0f}")
    print(f"    sample[0]={items[0]}")
    print(f"    sample[-1]={items[-1]}")


# 1. 东财（当日接口，周末返回最近交易日）
try:
    from company.line.eastmoney.ticks import fetch_ticks as em_ticks
    pack = em_ticks(CODE, pos=0)
    results["eastmoney"] = pack.get("items") or []
    print(f"eastmoney day={pack.get('day')} source={pack.get('source')}")
except Exception as exc:  # noqa: BLE001
    print(f"eastmoney FAILED: {exc}")
    results["eastmoney"] = []

# 2. 腾讯
try:
    from company.line.tencent.ticks import fetch_ticks as tx_ticks
    pack = tx_ticks(CODE, pos=0)
    results["tencent"] = pack.get("items") or []
    print(f"tencent day={pack.get('day')} source={pack.get('source')}")
except Exception as exc:  # noqa: BLE001
    print(f"tencent FAILED: {exc}")
    results["tencent"] = []

# 3. 同花顺（需登录，指定上一交易日）
try:
    from company.line.tonghuashun.hq_ticks import fetch_time_and_sales
    method, items = fetch_time_and_sales(CODE, day=DAY)
    results["tonghuashun"] = items
    print(f"tonghuashun method={method}")
except Exception as exc:  # noqa: BLE001
    print(f"tonghuashun FAILED: {type(exc).__name__}: {exc}")
    results["tonghuashun"] = []

for name, items in results.items():
    summarize(name, items)

# 交叉对比：东财 vs 腾讯按 (time, price, volume) 重合度
a = results["eastmoney"]
b = results["tencent"]
if a and b:
    ka = {(str(r.get("time")), r.get("price"), r.get("volume")) for r in a}
    kb = {(str(r.get("time")), r.get("price"), r.get("volume")) for r in b}
    print(f"overlap eastmoney∩tencent: {len(ka & kb)} / em={len(ka)} tx={len(kb)}")
    only_a = sorted(ka - kb)[:3]
    only_b = sorted(kb - ka)[:3]
    print(f"  only in eastmoney sample: {only_a}")
    print(f"  only in tencent sample: {only_b}")
