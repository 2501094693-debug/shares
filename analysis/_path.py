"""把 backend 加入 sys.path，供 analysis 包导入行情模块。"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"


def ensure_backend_path() -> Path:
    root = str(_BACKEND)
    if root not in sys.path:
        sys.path.insert(0, root)
    return _BACKEND
