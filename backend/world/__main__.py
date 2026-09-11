"""CLI 快速验证全球市场接口。"""

from __future__ import annotations

import json
import sys

from world.service import service


def main() -> None:
    section = (sys.argv[1] if len(sys.argv) > 1 else "overview").strip().lower()
    if section == "indices":
        data = service.indices(force=True)
    elif section == "rates":
        data = service.rates(force=True)
    elif section == "bonds":
        data = service.bonds(limit=30, force=True)
    elif section == "oil":
        data = service.oil(force=True)
    else:
        data = service.overview(rate_limit=12, bond_limit=20, force=True)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
