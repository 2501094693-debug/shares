"""兼容垫片：分价表已迁至 ``company.analysis.deal.price_levels``。

新代码请直接从新包导入；本文件仅保留旧路径可用。
"""

from company.analysis.deal.price_levels import (
    SHARES_PER_LOT,
    fetch_price_levels,
    fetch_price_levels_pack,
)

__all__ = [
    "SHARES_PER_LOT",
    "fetch_price_levels",
    "fetch_price_levels_pack",
]


def main() -> None:
    from company.analysis.deal.price_levels.__main__ import main as _main

    _main()


if __name__ == "__main__":
    main()
