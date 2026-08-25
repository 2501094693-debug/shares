"""python -m company.news.xueqiu"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.news.xueqiu import main

if __name__ == "__main__":
    raise SystemExit(main())
