"""CLI 快速验证全球市场接口。"""

from __future__ import annotations

import json
import sys

from world.bonds.service import service as bonds_service
from world.indices.service import service as indices_service
from world.oil.service import service as oil_service
from world.service import service


def main() -> None:
    section = (sys.argv[1] if len(sys.argv) > 1 else "overview").strip().lower()
    if section == "indices":
        data = indices_service.quotes(force=True)
    elif section == "rates":
        data = bonds_service.rates(force=True)
    elif section == "bonds":
        data = bonds_service.bonds(limit=30, force=True)
    elif section == "oil":
        data = oil_service.quotes(force=True)
    else:
        data = service.overview(rate_limit=12, bond_limit=20, force=True)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
