"""AT-SPI observation helpers (docs/gui-loop.md Observation).

Silvio's focus log (2026-09-10): success means a real ACTIVE transition on the
target app. "Already Ptyxis" does not prove the spike. Missing from the tree
(e.g. Nautilus) cannot become ACTIVE.
"""

from __future__ import annotations

import os
import time
from typing import Any


def _ensure_bus_address() -> None:
    if os.environ.get("AT_SPI_BUS_ADDRESS"):
        return
    try:
        from gi.repository import Gio

        addr = (
            Gio.DBusProxy.new_sync(
                Gio.bus_get_sync(Gio.BusType.SESSION, None),
                0,
                None,
                "org.a11y.Bus",
                "/org/a11y/bus",
                "org.a11y.Bus",
                None,
            )
            .call_sync("GetAddress", None, 0, 5000, None)
            .unpack()[0]
        )
        os.environ["AT_SPI_BUS_ADDRESS"] = addr
    except Exception:
        pass


def _init_atspi():
    _ensure_bus_address()
    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi

    Atspi.init()
    return Atspi


def app_match(name: str, app_id: str) -> bool:
    a = (name or "").lower()
    i = (app_id or "").lower()
    if not a or not i:
        return False
    if i in a or a in i:
        return True
    if "ptyxis" in i and "ptyxis" in a:
        return True
    if "nautilus" in i and "nautilus" in a:
        return True
    if "texteditor" in i.replace(".", "") and (
        "text-editor" in a or "texteditor" in a.replace(".", "")
    ):
        return True
    return False


def observe() -> dict[str, Any]:
    """Return Observation-like dict. Prefer client ACTIVE over gnome-shell stage."""
    try:
        Atspi = _init_atspi()
        desktop = Atspi.get_desktop(0)
    except Exception as e:
        return {
            "source": "a11y",
            "summary": f"a11y unavailable: {e}",
            "focused": None,
            "changed": False,
            "fingerprint": "",
            "apps": [],
            "in_tree": [],
        }

    frames: list[dict[str, Any]] = []
    focused_nodes: list[dict[str, Any]] = []
    apps: list[str] = []

    def walk_focused(obj, app_name: str, depth: int = 0) -> None:
        if obj is None or depth > 6:
            return
        try:
            st = obj.get_state_set()
            if st and st.contains(Atspi.StateType.FOCUSED):
                focused_nodes.append(
                    {
                        "app_id": app_name,
                        "role": obj.get_role_name(),
                        "name": obj.get_name(),
                    }
                )
                return
        except Exception:
            pass
        try:
            n = obj.get_child_count()
        except Exception:
            return
        for i in range(min(n, 25 if depth < 2 else 12)):
            try:
                walk_focused(obj.get_child_at_index(i), app_name, depth + 1)
            except Exception:
                pass

    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if not app:
            continue
        app_name = app.get_name() or "?"
        apps.append(app_name)
        walk_focused(app, app_name, 0)
        for j in range(app.get_child_count()):
            fr = app.get_child_at_index(j)
            if not fr:
                continue
            role = fr.get_role_name()
            if role not in {"frame", "window"}:
                continue
            st = fr.get_state_set()
            flags = [
                name
                for name in ("ACTIVE", "FOCUSED", "SHOWING", "VISIBLE", "ICONIFIED")
                if st.contains(getattr(Atspi.StateType, name))
            ]
            frames.append(
                {
                    "app_id": app_name,
                    "title": fr.get_name(),
                    "flags": flags,
                }
            )

    # Prefer non-shell ACTIVE/FOCUSED frames (Silvio's criterion).
    active_all = [f for f in frames if "ACTIVE" in f["flags"] or "FOCUSED" in f["flags"]]
    active_client = [f for f in active_all if (f.get("app_id") or "").lower() != "gnome-shell"]
    active = active_client or active_all

    client_focused = [
        n for n in focused_nodes if (n.get("app_id") or "").lower() != "gnome-shell"
    ]

    focused = None
    if active_client:
        focused = {
            "app_id": active_client[0]["app_id"],
            "title": active_client[0]["title"],
            "role": "frame",
            "name": active_client[0]["title"],
        }
    elif client_focused:
        focused = client_focused[0]
    elif active:
        focused = {
            "app_id": active[0]["app_id"],
            "title": active[0]["title"],
            "role": "frame",
            "name": active[0]["title"],
        }

    in_tree = sorted({a for a in apps if a and a.lower() != "gnome-shell"})

    if focused:
        summary = f"{focused.get('app_id')}: {focused.get('name') or focused.get('title')}"
    elif frames:
        summary = f"{len(frames)} frames; no client ACTIVE (apps={in_tree})"
    else:
        summary = f"no frames; apps={in_tree}"

    fingerprint = "||".join(
        f"{f['app_id']}|{f['title']}|{','.join(f['flags'])}" for f in frames
    )

    return {
        "source": "a11y",
        "summary": summary,
        "focused": focused,
        "changed": False,
        "fingerprint": fingerprint,
        "apps": apps,
        "in_tree": in_tree,
        "frames": frames,
    }


def target_in_tree(obs: dict[str, Any], app_id: str) -> bool:
    for name in obs.get("apps") or []:
        if app_match(str(name), app_id):
            return True
    for fr in obs.get("frames") or []:
        if app_match(str(fr.get("app_id") or ""), app_id):
            return True
    return False


def target_active(obs: dict[str, Any], app_id: str) -> bool:
    """True if a non-shell frame for app_id is ACTIVE/FOCUSED."""
    for fr in obs.get("frames") or []:
        if (fr.get("app_id") or "").lower() == "gnome-shell":
            continue
        flags = fr.get("flags") or []
        if "ACTIVE" not in flags and "FOCUSED" not in flags:
            continue
        if app_match(str(fr.get("app_id") or ""), app_id):
            return True
    foc = obs.get("focused") or {}
    if (foc.get("app_id") or "").lower() == "gnome-shell":
        return False
    return app_match(str(foc.get("app_id") or ""), app_id)


def already_focused(pre: dict[str, Any], step: dict[str, Any]) -> bool:
    return target_active(pre, step.get("app_id") or "")


def changed(pre: dict[str, Any], post: dict[str, Any], step: dict[str, Any]) -> bool:
    """True only on a real transition: target not ACTIVE before, ACTIVE after."""
    app_id = step.get("app_id") or ""
    if not app_id:
        return False
    if already_focused(pre, step):
        return False
    return target_active(post, app_id)


def wait_until_in_tree(app_id: str, timeout_s: float = 8.0) -> dict[str, Any]:
    """Poll AT-SPI until app frames appear or timeout."""
    deadline = time.time() + timeout_s
    last = observe()
    while time.time() < deadline:
        last = observe()
        if target_in_tree(last, app_id):
            return last
        time.sleep(0.25)
    return last
