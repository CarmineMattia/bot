"""Null overlay: print OverlayShow / OverlayClear as one line (docs/overlay.md)."""

from __future__ import annotations

import json
import sys
from typing import Any


def show(payload: dict[str, Any]) -> None:
    line = {"overlay": "show", **payload}
    print(json.dumps(line), file=sys.stderr, flush=True)


def clear(reason: str = "done") -> None:
    print(json.dumps({"overlay": "clear", "reason": reason}), file=sys.stderr, flush=True)
