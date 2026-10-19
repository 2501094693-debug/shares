"""CLI 入口：``python -m company.analysis.businessoverview 600990``

具体实现见 :mod:`company.analysis.businessoverview.interfaces.__main__`。
"""

from __future__ import annotations

from company.analysis.businessoverview.interfaces.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
