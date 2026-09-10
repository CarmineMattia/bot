"""Shared ydotool helpers (uinput via ydotoold)."""

from __future__ import annotations

import os
import subprocess
import time

DEFAULT_SOCKET = os.path.expanduser("~/.ydotool_socket")
RUNTIME_SOCKET = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), ".ydotool_socket")

KEY_CODES = {
    **{chr(ord("a") + i): code for i, code in enumerate(
        (30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50, 49, 24, 25, 16, 19, 31, 20, 22, 47, 17, 45, 21, 44)
    )},
    **{str(i): code for i, code in enumerate((11, 2, 3, 4, 5, 6, 7, 8, 9, 10))},
    "ctrl": 29,
    "control": 29,
    "shift": 42,
    "alt": 56,
    "super": 125,
    "meta": 125,
    "enter": 28,
    "tab": 15,
    "esc": 1,
    "escape": 1,
    "space": 57,
    "f4": 62,
}



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

def hotkey(keys: list[str]) -> str | None:
    """Press a key chord using Linux input-event key codes."""
    normalized = [str(key).strip().lower() for key in keys]
    if len(normalized) < 2:
        return "Hotkey requires at least two keys"
    if len(set(normalized)) != len(normalized):
        return "Hotkey contains duplicate keys"
    unknown = [key for key in normalized if key not in KEY_CODES]
    if unknown:
        return f"Unknown hotkey keys: {', '.join(unknown)}"
    codes = [KEY_CODES[key] for key in normalized]
    # press modifiers+key down then up in reverse
    downs = [f"{c}:1" for c in codes]
    ups = [f"{c}:0" for c in reversed(codes)]
    return run("key", *downs, *ups)

