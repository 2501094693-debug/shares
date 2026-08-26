"""python -m company.emotion"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.emotion import main

if __name__ == "__main__":
    raise SystemExit(main())
