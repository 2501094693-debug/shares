"""临时对照：资金动向 vs 逐笔还原大单。"""
from __future__ import annotations

from collections import defaultdict

from company.analysis.deal.sources import load_big_deals, load_ticks
from company.analysis.deal.window import (
    build_windows,
    normalize_orders,
    place_orders,
    reconstruct_windows,
)


def main() -> None:
    big, _ = load_big_deals("600990")
    ticks = load_ticks("600990")
    orders = normalize_orders(big.get("items"), view="all")
    windows, _ = build_windows(ticks.get("items"))
    alloc, unplaced = place_orders(windows, orders)

    print("orders", len(orders), "unplaced", unplaced)
    got: dict[str, dict] = defaultdict(lambda: {"lots": 0.0, "times": []})
    for idx, items in alloc.items():
        for it in items:
            oid = it["order"]["order_id"]
            got[oid]["lots"] += it["lots"]
            got[oid]["times"].append(windows[idx]["time"])

    print("--- placement ---")
    ok_n = 0
    for o in orders:
        g = got.get(o["order_id"], {"lots": 0, "times": []})
        last = max(g["times"]) if g["times"] else None
        # first stamp >= T
        deadline = next((w["time"] for w in windows if w["time"] >= o["time"]), None)
        pinned = last == deadline
        lots_ok = abs(g["lots"] - o["lots"]) < 1e-6
        flag = "OK" if pinned and lots_ok else "BAD"
        if flag == "OK":
            ok_n += 1
        print(
            flag,
            o["order_id"],
            o["side"],
            o["view"],
            "need",
            o["lots"],
            "got",
            g["lots"],
            "src_t",
            o["time"],
            "deadline",
            deadline,
            "last_fill",
            last,
            "px",
            o["price"],
        )
    print(f"pinned+lots OK: {ok_n}/{len(orders)}")

    pack = reconstruct_windows(ticks.get("items"), big.get("items"), code="600990", view="all")
    print("summary", pack.get("summary"))
    print("reconcile", {k: pack["reconcile"][k] for k in ("unplaced_count", "lot_mismatch_windows", "infeasible_windows")})

    # 按 order_id 汇总还原手数 / 最后时间 / 价格
    agg: dict[str, dict] = defaultdict(lambda: {"lots": 0.0, "times": [], "prices": []})
    for r in pack.get("rows") or []:
        if r.get("kind") != "order":
            continue
        for key in (r.get("order_id"), r.get("order_id_peer")):
            if not key:
                continue
            a = agg[str(key)]
            a["lots"] += r["lots"]
            a["times"].append(r["time"])
            a["prices"].append(r.get("price"))

    print("--- reconstruct vs source ---")
    by_id = {o["order_id"]: o for o in orders}
    for oid, o in by_id.items():
        a = agg.get(oid, {"lots": 0, "times": [], "prices": []})
        last = max(a["times"]) if a["times"] else None
        print(
            oid,
            o["side"],
            "src",
            o["lots"],
            o["time"],
            o["price"],
            "| recon",
            a["lots"],
            last,
            a["prices"][:1],
        )


if __name__ == "__main__":
    main()
