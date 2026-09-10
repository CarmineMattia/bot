"""Overlay client (docs/overlay.md).

Spawns GTK overlay server when possible; always mirrors to stderr (null log).
Set BOT_OVERLAY=0 to disable the UI process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_proc: subprocess.Popen[str] | None = None
_ui_failed = False


def _server_cmd() -> list[str]:
    root = Path(__file__).resolve().parent
    return [sys.executable, str(root / "overlay_server.py")]


def _ensure_ui() -> bool:
    global _proc, _ui_failed
    if os.environ.get("BOT_OVERLAY", "1") in {"0", "false", "no"}:
        return False
    if _ui_failed:
        return False
    if _proc is not None and _proc.poll() is None:
        return True
    if _proc is not None and _proc.poll() is not None:
        err = ""
        try:
            if _proc.stderr:
                err = _proc.stderr.read() or ""
        except Exception:
            pass
        print(
            json.dumps({"overlay": "ui_dead", "code": _proc.returncode, "stderr": err[-400:]}),
            file=sys.stderr,
            flush=True,
        )
        _ui_failed = True
        _proc = None
        return False
    try:
        _proc = subprocess.Popen(
            _server_cmd(),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except Exception as e:
        print(json.dumps({"overlay": "ui_error", "error": str(e)}), file=sys.stderr, flush=True)
        _ui_failed = True
        _proc = None
        return False
    # Wait briefly for activate (or instant death on missing deps).
    time.sleep(0.25)
    if _proc.poll() is not None:
        err = ""
        try:
            if _proc.stderr:
                err = _proc.stderr.read() or ""
        except Exception:
            pass
        print(
            json.dumps({"overlay": "ui_dead", "code": _proc.returncode, "stderr": err[-400:]}),
            file=sys.stderr,
            flush=True,
        )
        _ui_failed = True
        _proc = None
        return False
    return True


def _send(msg: dict[str, Any]) -> None:
    global _proc, _ui_failed
    if not _ensure_ui() or _proc is None or _proc.stdin is None:
        return
    try:
        _proc.stdin.write(json.dumps(msg) + "\n")
        _proc.stdin.flush()
    except Exception as e:
        print(json.dumps({"overlay": "ui_error", "error": str(e)}), file=sys.stderr, flush=True)
        _ui_failed = True
        try:
            _proc.kill()
        except Exception:
            pass
        _proc = None


def show(payload: dict[str, Any]) -> None:
    line = {"overlay": "show", **payload}
    print(json.dumps(line), file=sys.stderr, flush=True)
    _send({"cmd": "show", **payload})


def clear(reason: str = "done") -> None:
    print(json.dumps({"overlay": "clear", "reason": reason}), file=sys.stderr, flush=True)
    _send({"cmd": "clear", "reason": reason})


def shutdown() -> None:
    global _proc
    if _proc is None:
        return
    try:
        if _proc.stdin:
            _proc.stdin.close()
        _proc.wait(timeout=2)
    except Exception:
        try:
            _proc.kill()
        except Exception:
            pass
    _proc = None
