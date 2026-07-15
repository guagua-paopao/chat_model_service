from __future__ import annotations

import sys
from pathlib import Path

FAKE_IDP_SOURCE = Path(__file__).parents[1] / "apps" / "fake-idp" / "src"
sys.path.insert(0, str(FAKE_IDP_SOURCE))
