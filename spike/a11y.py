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


def target_hint_for_step(step: dict[str, Any] | None) -> dict[str, Any] | None:
    """Best-effort AT-SPI frame/control rect for overlay."""
    if not step:
        return None
    stype = step.get("type")
    if stype == "ClickA11y":
        hit = find_a11y_target(
            role=str(step.get("role") or ""),
            name=str(step.get("name") or ""),
            window=step.get("window"),
        )
        if not hit:
            return None
        return {
            "kind": "rect",
            "x": hit["x"],
            "y": hit["y"],
            "w": hit["w"],
            "h": hit["h"],
        }
    if stype == "TypeText":
        foc = type_target()
        if foc and foc.get("w", 0) > 1:
            return {
                "kind": "rect",
                "x": foc["x"],
                "y": foc["y"],
                "w": foc["w"],
                "h": foc["h"],
            }
        return None
    if stype != "FocusWindow":
        return None
    app_id = step.get("app_id") or ""
    try:
        Atspi = _init_atspi()
        desk = Atspi.get_desktop(0)
        for i in range(desk.get_child_count()):
            app = desk.get_child_at_index(i)
            if not app or not app_match(app.get_name() or "", app_id):
                continue
            for j in range(app.get_child_count()):
                fr = app.get_child_at_index(j)
                if not fr or fr.get_role_name() not in {"frame", "window"}:
                    continue
                e = fr.get_extents(Atspi.CoordType.SCREEN)
                if e.width <= 1 or e.height <= 1:
                    continue
                return {
                    "kind": "rect",
                    "x": int(e.x),
                    "y": int(e.y),
                    "w": int(e.width),
                    "h": int(e.height),
                }
    except Exception:
        return None
    return None


EDITABLE_ROLES = {
    "entry",
    "password text",
    "text",
    "terminal",
    "document text",
    "edit bar",
    "combo box",
}

# Apps that accept keyboard input even when AT-SPI hides the editable child
# (Ptyxis often exposes only frame → panel).
TYPEABLE_APP_HINTS = (
    ("ptyxis", "terminal"),
    ("org.gnome.texteditor", "document text"),
    ("gnome-text-editor", "document text"),
    ("gedit", "document text"),
    ("firefox", "entry"),
    ("chrom", "entry"),
)


def type_target() -> dict[str, Any] | None:
    """Best place to type: focused editable, else ACTIVE typeable app frame."""
    foc = focused_editable()
    if foc:
        return foc
    obs = observe()
    for fr in obs.get("frames") or []:
        flags = fr.get("flags") or []
        if "ACTIVE" not in flags:
            continue
        app = str(fr.get("app_id") or "")
        al = app.lower().replace(".", "")
        for hint, role in TYPEABLE_APP_HINTS:
            hl = hint.lower().replace(".", "")
            if hl in al or al in hl:
                return {
                    "app_id": app,
                    "role": role,
                    "name": fr.get("title") or "",
                    "x": 0,
                    "y": 0,
                    "w": 0,
                    "h": 0,
                    "synthetic": True,
                }
    return None


def focused_editable() -> dict[str, Any] | None:
    """Return focused editable node + extents, or None."""
    try:
        Atspi = _init_atspi()
        desk = Atspi.get_desktop(0)
    except Exception:
        return None

    found: dict[str, Any] | None = None

    def walk(obj, app_name: str, depth: int = 0) -> None:
        nonlocal found
        if found is not None or obj is None or depth > 10:
            return
        try:
            role = (obj.get_role_name() or "").lower()
            st = obj.get_state_set()
            if (
                role in EDITABLE_ROLES
                and st
                and st.contains(Atspi.StateType.FOCUSED)
                and (app_name or "").lower() != "gnome-shell"
            ):
                e = obj.get_extents(Atspi.CoordType.SCREEN)
                found = {
                    "app_id": app_name,
                    "role": role,
                    "name": obj.get_name() or "",
                    "x": int(e.x),
                    "y": int(e.y),
                    "w": int(e.width),
                    "h": int(e.height),
                }
                return
        except Exception:
            pass
        try:
            n = obj.get_child_count()
        except Exception:
            return
        for i in range(min(n, 40 if depth < 2 else 20)):
            try:
                walk(obj.get_child_at_index(i), app_name, depth + 1)
            except Exception:
                pass

    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if not app:
            continue
        walk(app, app.get_name() or "?", 0)
        if found:
            break
    return found


def find_a11y_target(
    *,
    role: str,
    name: str,
    window: str | None = None,
) -> dict[str, Any] | None:
    """Find first SHOWING control matching role+name (case-insensitive substring)."""
    role_l = (role or "").lower().strip()
    name_l = (name or "").lower().strip()
    if not role_l or not name_l:
        return None
    try:
        Atspi = _init_atspi()
        desk = Atspi.get_desktop(0)
    except Exception:
        return None

    hits: list[dict[str, Any]] = []

    def walk(obj, app_name: str, depth: int = 0) -> None:
        if obj is None or depth > 12:
            return
        try:
            r = (obj.get_role_name() or "").lower()
            n = (obj.get_name() or "").lower()
            st = obj.get_state_set()
            showing = bool(st and st.contains(Atspi.StateType.SHOWING))
            if (
                showing
                and (app_name or "").lower() != "gnome-shell"
                and role_l in r
                and name_l in n
            ):
                e = obj.get_extents(Atspi.CoordType.SCREEN)
                if e.width > 1 and e.height > 1:
                    hits.append(
                        {
                            "app_id": app_name,
                            "role": r,
                            "name": obj.get_name() or "",
                            "x": int(e.x),
                            "y": int(e.y),
                            "w": int(e.width),
                            "h": int(e.height),
                            "cx": int(e.x + e.width / 2),
                            "cy": int(e.y + e.height / 2),
                            "_obj": obj,
                        }
                    )
        except Exception:
            pass
        try:
            nch = obj.get_child_count()
        except Exception:
            return
        for i in range(min(nch, 50 if depth < 2 else 25)):
            try:
                walk(obj.get_child_at_index(i), app_name, depth + 1)
            except Exception:
                pass

    for i in range(desk.get_child_count()):
        app = desk.get_child_at_index(i)
        if not app:
            continue
        walk(app, app.get_name() or "?", 0)

    if window:
        w = window.lower()
        filtered = [
            h
            for h in hits
            if w in (h.get("app_id") or "").lower() or w in (h.get("name") or "").lower()
        ]
        if filtered:
            hits = filtered

    if not hits:
        return None
    hits.sort(
        key=lambda h: (
            0 if h["name"].lower() == name_l else 1,
            h["w"] * h["h"],
        )
    )
    return hits[0]


def try_a11y_click(obj) -> bool:  # noqa: ANN001
    """Invoke click/press/activate action on an AT-SPI node if present."""
    try:
        ai = obj.get_action_iface()
        if not ai:
            return False
        prefer = ("click", "press", "activate", "default.activate", "Jump")
        names = []
        for k in range(ai.get_n_actions()):
            try:
                names.append(ai.get_action_name(k) or "")
            except Exception:
                names.append("")
        idx = None
        for want in prefer:
            for k, nm in enumerate(names):
                if nm.lower() == want.lower() or want.lower() in nm.lower():
                    idx = k
                    break
            if idx is not None:
                break
        if idx is None and names:
            idx = 0
        if idx is None:
            return False
        return bool(ai.do_action(idx))
    except Exception:
        return False


def fingerprint_delta(pre: dict[str, Any], post: dict[str, Any]) -> bool:
    return (pre.get("fingerprint") or "") != (post.get("fingerprint") or "") or (
        pre.get("summary") or ""
    ) != (post.get("summary") or "")


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
