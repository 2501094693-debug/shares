#!/usr/bin/env python3
"""产业链分析智能体 CLI 入口。

用法:
    python explain_chain.py 000338
    python explain_chain.py 潍柴动力 --stream
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.chain_analyst.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())
