"""CLI 入口"""
from __future__ import annotations

import argparse
import sys

from .api import risk_scan_cninfo_only_fetch_json, risk_scan_cninfo_only_fetch_md


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Risk assessment using only cninfo.fetch_announcements")
    p.add_argument("code", help="股票代码，如 000001/600519")
    p.add_argument("--format", choices=["md", "json"], default="md")
    args = p.parse_args(argv)

    try:
        if args.format == "json":
            print(risk_scan_cninfo_only_fetch_json(args.code))
        else:
            print(risk_scan_cninfo_only_fetch_md(args.code))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
