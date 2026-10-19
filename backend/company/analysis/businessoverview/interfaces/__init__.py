"""对外暴露的接口层：HTTP 路由 + CLI。

    from company.analysis.businessoverview.interfaces import router
    from company.analysis.businessoverview.interfaces import main as cli_main

具体实现在 :mod:`api`（HTTP）与 :mod:`__main__`（CLI）。
"""

from __future__ import annotations

from company.analysis.businessoverview.interfaces.api import router
from company.analysis.businessoverview.interfaces.__main__ import main as cli_main

__all__ = ["router", "cli_main"]
