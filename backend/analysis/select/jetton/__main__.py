"""python -m analysis.select.jetton 600519 2024-01-01 2024-12-31 --f triangle --k flat"""
from __future__ import annotations
import argparse, json
from analysis.select.jetton.service import run_symbol

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", default="600519", nargs="?")
    ap.add_argument("start", default="2024-01-01", nargs="?")
    ap.add_argument("end", default="2024-12-31", nargs="?")
    ap.add_argument("--f", default="triangle")
    ap.add_argument("--k", default="flat")
    ap.add_argument("--base", type=float, default=0.05)
    ap.add_argument("--tick", type=float, default=None)
    ap.add_argument("--rel", type=float, default=0.001)
    ap.add_argument("--min-tick", type=float, default=0.01)
    ap.add_argument("--bins", type=int, default=None)
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--keep-every", type=int, default=1)
    ap.add_argument("--details", action="store_true")
    a = ap.parse_args()
    kw = dict(f_mode=a.f, k_kind=a.k, base=a.base, tick=a.tick,
              rel=a.rel, min_tick=getattr(a, "min_tick"),
              return_history=a.history, keep_every=a.keep_every,
              include_details=a.details)
    if a.bins is not None:
        kw["bins"] = a.bins
    out = run_symbol(a.symbol, a.start, a.end, **kw)
    print(json.dumps(out["stats"], ensure_ascii=False, indent=2, default=float))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
