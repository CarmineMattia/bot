"""Shared ydotool helpers (uinput via ydotoold)."""

from __future__ import annotations

import os
import subprocess
import time

DEFAULT_SOCKET = os.path.expanduser("~/.ydotool_socket")
RUNTIME_SOCKET = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), ".ydotool_socket")


def socket_path() -> str:
    env = os.environ.get("YDOTOOL_SOCKET")
    if env:
        return env
    if os.path.exists(RUNTIME_SOCKET):
        return RUNTIME_SOCKET
    return DEFAULT_SOCKET


def ensure_ydotoold() -> str | None:
    sock = socket_path()
    os.environ["YDOTOOL_SOCKET"] = sock
    if os.path.exists(sock):
        return None
    try:
        subprocess.Popen(
            ["ydotoold", "-p", sock, "-P", "0666"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        return "ydotool/ydotoold not installed (dnf install ydotool)"
    except Exception as e:
        return f"failed to start ydotoold: {e}"
    for _ in range(20):
        if os.path.exists(sock):
            return None
        time.sleep(0.1)
    return f"ydotoold socket not ready: {sock}"


def run(*args: str, timeout: float = 15.0) -> str | None:
    """Run ydotool. Return error string or None."""
    env = os.environ.copy()
    env["YDOTOOL_SOCKET"] = socket_path()
    try:
        r = subprocess.run(
            ["ydotool", *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except FileNotFoundError:
        return "ydotool not installed"
    except Exception as e:
        return str(e)
    if r.returncode != 0:
        return (r.stderr or r.stdout or f"ydotool exit {r.returncode}").strip()
    return None


def type_text(text: str, *, key_delay_ms: int = 12) -> str | None:
    err = ensure_ydotoold()
    if err:
        return err
    return run("type", "--key-delay", str(key_delay_ms), "--", text)


def key_enter() -> str | None:
    err = ensure_ydotoold()
    if err:
        return err
    return run("key", "28:1", "28:0")


def click_abs(x: int, y: int) -> str | None:
    err = ensure_ydotoold()
    if err:
        return err
    move = run("mousemove", "--absolute", "-x", str(int(x)), "-y", str(int(y)))
    if move:
        return move
    time.sleep(0.05)
    # 0xC0 = left down+up (0x00 | 0x40 down bit pattern used by ydotool click)
    return run("click", "0xC0")
