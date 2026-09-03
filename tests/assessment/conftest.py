from __future__ import annotations

import sys
from pathlib import Path

HUB = Path(__file__).resolve().parents[2] / "services" / "hub"
if str(HUB) not in sys.path:
    sys.path.insert(0, str(HUB))
