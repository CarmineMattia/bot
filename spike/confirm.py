"""Policy confirm / abort gate (docs/policy.md, docs/overlay.md).

Ask mode blocks until explicit confirm. Auto announce pause is abortible.
Non-interactive runs need --yes / --no or BOT_CONFIRM=yes|no.
"""

from __future__ import annotations

import os
import select
import sys
import time
from typing import Literal

ConfirmResult = Literal["confirm", "abort", "timeout", "need_tty"]


def _env_forced() -> ConfirmResult | None:
    raw = (os.environ.get("BOT_CONFIRM") or "").strip().lower()
    if raw in {"1", "y", "yes", "confirm", "ok", "true"}:
        return "confirm"
    if raw in {"0", "n", "no", "abort", "cancel", "false"}:
        return "abort"
    return None


def wait_confirm(
    *,
    prompt: str,
    forced: str | None = None,
    timeout_s: float = 60.0,
) -> ConfirmResult:
    """Wait for user confirm. forced: 'yes' | 'no' | None."""
    if forced in {"yes", "y", "confirm"}:
        return "confirm"
    if forced in {"no", "n", "abort"}:
        return "abort"
    env = _env_forced()
    if env is not None:
        return env

    if not sys.stdin.isatty():
        return "need_tty"

    print(prompt, file=sys.stderr, flush=True)
    print("  confirm: y / yes    abort: n / no / q", file=sys.stderr, flush=True)

    deadline = time.monotonic() + max(0.1, timeout_s)
    buf = ""
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        ready, _, _ = select.select([sys.stdin], [], [], min(0.5, remaining))
        if not ready:
            continue
        chunk = sys.stdin.readline()
        if chunk == "":
            return "need_tty"
        buf = chunk.strip().lower()
        if buf in {"y", "yes", "ok", "confirm"}:
            return "confirm"
        if buf in {"n", "no", "q", "abort", "cancel"}:
            return "abort"
        print("  type y or n", file=sys.stderr, flush=True)
    return "timeout"


def abortable_pause(pause_ms: int) -> bool:
    """Sleep pause_ms; return True if user aborted (q/n/abort on stdin)."""
    if pause_ms <= 0:
        return False
    if not sys.stdin.isatty():
        time.sleep(pause_ms / 1000.0)
        return False
    deadline = time.monotonic() + pause_ms / 1000.0
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        ready, _, _ = select.select([sys.stdin], [], [], min(0.1, max(0.0, remaining)))
        if not ready:
            continue
        line = sys.stdin.readline().strip().lower()
        if line in {"q", "n", "no", "abort", "cancel"}:
            return True
        # ignore other input during short announce pause
    return False
