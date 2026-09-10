"""Raise an existing GNOME window without opening a new one.

Strategy (verified 2026-09-10): ydotool Super → type app name → Enter in Overview.
Keeps AT-SPI frame count stable while flipping ACTIVE.

Requires `ydotoold` (uinput) and `YDOTOOL_SOCKET` (default ~/.ydotool path).
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from . import a11y

# Overview search strings that resolve to a running app (not "New Window").
OVERVIEW_QUERY = {
    "org.gnome.Ptyxis": "Ptyxis",
    "org.gnome.Nautilus": "Files",
    "org.gnome.TextEditor": "Text Editor",
}

DEFAULT_SOCKET = os.path.expanduser("~/.ydotool_socket")
# Prefer XDG runtime if present (what we start in sessions).
RUNTIME_SOCKET = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), ".ydotool_socket")


def _frame_count(obs: dict[str, Any], app_id: str) -> int:
    return sum(
        1
        for fr in obs.get("frames") or []
        if a11y.app_match(str(fr.get("app_id") or ""), app_id)
    )


def _socket_path() -> str:
    env = os.environ.get("YDOTOOL_SOCKET")
    if env:
        return env
    if os.path.exists(RUNTIME_SOCKET):
        return RUNTIME_SOCKET
    return DEFAULT_SOCKET


def ensure_ydotoold() -> str | None:
    """Return error or None. Starts user ydotoold if socket missing."""
    sock = _socket_path()
    os.environ["YDOTOOL_SOCKET"] = sock
    if os.path.exists(sock):
        return None
    # Try start daemon (user ACL on /dev/uinput required)
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


def _ydo(*args: str) -> str | None:
    env = os.environ.copy()
    env["YDOTOOL_SOCKET"] = _socket_path()
    try:
        r = subprocess.run(
            ["ydotool", *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
    except FileNotFoundError:
        return "ydotool not installed"
    except Exception as e:
        return str(e)
    if r.returncode != 0:
        return (r.stderr or r.stdout or f"ydotool exit {r.returncode}").strip()
    return None


def _overview_showing() -> bool:
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi

        Atspi = a11y._init_atspi()
        desk = Atspi.get_desktop(0)
    except Exception:
        return False
    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if not app or (app.get_name() or "") != "gnome-shell":
            continue
        stack: list[tuple[Any, int]] = [(app, 0)]
        while stack:
            obj, depth = stack.pop()
            if not obj or depth > 8:
                continue
            try:
                if (obj.get_name() or "") == "Overview":
                    st = obj.get_state_set()
                    return bool(st.contains(Atspi.StateType.SHOWING))
            except Exception:
                pass
            try:
                n = min(obj.get_child_count(), 40)
            except Exception:
                continue
            for j in range(n):
                try:
                    stack.append((obj.get_child_at_index(j), depth + 1))
                except Exception:
                    pass
    return False


def _open_overview() -> str | None:
    for _ in range(2):
        err = _ydo("key", "1:1", "1:0")  # Esc
        if err:
            return err
        time.sleep(0.12)
    for _ in range(3):
        err = _ydo("key", "125:1", "125:0")  # Super_L
        if err:
            return err
        time.sleep(0.7)
        if _overview_showing():
            return None
    return "could not open GNOME Overview (Super)"


def raise_existing(app_id: str) -> str | None:
    """Bring an already-open app to front. None on best-effort success path.

    Caller must verify ACTIVE transition + stable frame count.
    """
    query = OVERVIEW_QUERY.get(app_id)
    if not query:
        return f"no overview query mapped for {app_id}"

    daemon_err = ensure_ydotoold()
    if daemon_err:
        return daemon_err

    frames_before = _frame_count(a11y.observe(), app_id)
    if frames_before < 1:
        return f"no existing frames for {app_id}; cannot raise-only"

    ov_err = _open_overview()
    if ov_err:
        return ov_err

    type_err = _ydo("type", query)
    if type_err:
        return type_err
    time.sleep(0.65)
    enter_err = _ydo("key", "28:1", "28:0")  # Enter
    if enter_err:
        return enter_err
    time.sleep(0.9)
    if _overview_showing():
        _ydo("key", "1:1", "1:0")
        time.sleep(0.25)

    post = a11y.observe()
    frames_after = _frame_count(post, app_id)
    if frames_after > frames_before:
        return (
            f"overview raise opened extra frames for {app_id} "
            f"({frames_before}→{frames_after})"
        )
    if not a11y.target_active(post, app_id):
        return (
            f"overview raise did not activate {app_id}; "
            f"focus={post.get('summary')!r}"
        )
    return None
