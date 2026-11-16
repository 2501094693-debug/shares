"""兼容旧入口：实际实现见 ``company.analysis.deal.fundflow``。"""

from __future__ import annotations

from company.analysis.deal.fundflow.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())