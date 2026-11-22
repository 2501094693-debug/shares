"""MACD 金叉 + 稳定区间筛选（项目根目录入口）。

用法::

    python scripts/macd_stable_screen.py
    python scripts/macd_stable_screen.py --codes 600519,000001
    python scripts/macd_stable_screen.py --to-mine
    python scripts/macd_stable_screen.py --group MACD金叉_2026-11-21

也可在 backend 目录下::

    python -m analysis.macd --to-mine
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve()
_ROOT = _SCRIPT.parents[1]
_BACKEND = _ROOT / "backend"
for path in (_BACKEND, _ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from analysis.macd.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
