"""Actuation: FocusWindow = raise existing windows only (no --new-window).

Silvio (2026-09-10): --new-window fallbacks made ACTIVE transitions by *opening*
new Home/Ptyxis frames. FocusWindow must not do that when frames already exist.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from . import a11y
from . import raise_existing as raise_mod


DESKTOP_FILES = {
    "org.gnome.Ptyxis": "org.gnome.Ptyxis.desktop",
    "org.gnome.Nautilus": "org.gnome.Nautilus.desktop",
    "org.gnome.TextEditor": "org.gnome.TextEditor.desktop",
}


def _app_object_path(app_id: str) -> str:
    return "/" + app_id.replace(".", "/")


def _matches_app(app_name: str, app_id: str) -> bool:
    return a11y.app_match(app_name, app_id)


def target_frame_count(obs: dict[str, Any], app_id: str) -> int:
    return sum(
        1
        for fr in obs.get("frames") or []
        if _matches_app(str(fr.get("app_id") or ""), app_id)
    )


def _activate_dbus(app_id: str) -> str | None:
    try:
        from gi.repository import Gio, GLib
    except Exception as e:  # pragma: no cover
        return f"PyGObject required: {e}"
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        proxy = Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            app_id,
            _app_object_path(app_id),
            "org.freedesktop.Application",
            None,
        )
        proxy.call_sync(
            "Activate",
            GLib.Variant("(a{sv})", ({},)),
            Gio.DBusCallFlags.NONE,
            5000,
            None,
        )
    except Exception as e:
        return f"Activate failed for {app_id}: {e}"
    return None


def _launch_desktop(app_id: str) -> str | None:
    """Start an app that has *no* AT-SPI frames yet (first window only)."""
    desktop = DESKTOP_FILES.get(app_id)
    if not desktop:
        return f"no desktop file mapping for {app_id}"
    if shutil.which("gtk-launch"):
        try:
            subprocess.Popen(
                ["gtk-launch", desktop],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return None
        except Exception as e:
            return f"gtk-launch failed: {e}"
    if shutil.which("gio"):
        try:
            subprocess.Popen(
                ["gio", "launch", f"/usr/share/applications/{desktop}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return None
        except Exception as e:
            return f"gio launch failed: {e}"
    return "neither gtk-launch nor gio available"


def _rebind_a11y(app_id: str) -> str | None:
    """Restart apps that never registered on AT-SPI (only when zero frames)."""
    if app_id == "org.gnome.Nautilus":
        subprocess.run(["killall", "nautilus"], check=False, capture_output=True)
        time.sleep(0.4)
        try:
            subprocess.Popen(
                ["nautilus", "--new-window", str(Path.home())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            return f"nautilus relaunch failed: {e}"
        return None
    if app_id == "org.gnome.TextEditor":
        subprocess.run(["killall", "gnome-text-editor"], check=False, capture_output=True)
        time.sleep(0.4)
        return _launch_desktop(app_id)
    if app_id == "org.gnome.Ptyxis":
        return "ptyxis missing from AT-SPI; open a Ptyxis window manually with a11y on"
    return f"no a11y-rebind recipe for {app_id}"


def ensure_in_tree(
    app_id: str,
    timeout_s: float = 8.0,
    *,
    allow_launch: bool = True,
    allow_rebind: bool | None = None,
) -> str | None:
    """Ensure at least one frame exists. Does nothing if already in tree.

    If allow_launch is False (raise-only mode), missing frames are an error —
    never gtk-launch / --new-window / rebind.

    killall-based a11y rebind is off by default (destructive on auto policy).
    Opt in with allow_rebind=True or BOT_ALLOW_REBIND=1.
    """
    if allow_rebind is None:
        allow_rebind = os.environ.get("BOT_ALLOW_REBIND", "").lower() in {
            "1",
            "true",
            "yes",
        }

    obs = a11y.observe()
    if target_frame_count(obs, app_id) > 0:
        return None
    if not allow_launch:
        return (
            f"{app_id} has 0 AT-SPI frames (raise-only). "
            f"Open exactly one window manually first. in_tree={obs.get('in_tree')}"
        )
    launch_err = _launch_desktop(app_id)
    _activate_dbus(app_id)
    obs = a11y.wait_until_in_tree(app_id, timeout_s=timeout_s)
    if target_frame_count(obs, app_id) > 0:
        return None

    if not allow_rebind:
        return (
            f"{app_id} not in AT-SPI tree after launch "
            f"(launch={launch_err}; in_tree={obs.get('in_tree')}). "
            "Refusing killall rebind on auto path. "
            "Restart the app with toolkit-accessibility on, or set BOT_ALLOW_REBIND=1."
        )

    rebind_err = _rebind_a11y(app_id)
    obs = a11y.wait_until_in_tree(app_id, timeout_s=timeout_s)
    if target_frame_count(obs, app_id) > 0:
        return None

    hint = f"launch={launch_err}; rebind={rebind_err}"
    return (
        f"{app_id} not in AT-SPI tree after {timeout_s:.0f}s ({hint}; "
        f"in_tree={obs.get('in_tree')}). "
        "Apps started before toolkit-accessibility often need a restart."
    )


def _activate_atspi(app_id: str) -> str | None:
    try:
        Atspi = a11y._init_atspi()
        desktop = Atspi.get_desktop(0)
    except Exception as e:
        return f"AT-SPI init failed: {e}"

    errors: list[str] = []
    activated = False
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if not app:
            continue
        if not _matches_app(app.get_name() or "", app_id):
            continue
        for j in range(app.get_child_count()):
            fr = app.get_child_at_index(j)
            if not fr or fr.get_role_name() not in {"frame", "window"}:
                continue
            try:
                ai = fr.get_action_iface()
                if not ai:
                    continue
                idx = None
                for k in range(ai.get_n_actions()):
                    try:
                        name = ai.get_action_name(k)
                    except Exception:
                        name = ""
                    if name in {"default.activate", "activate", "Activate"}:
                        idx = k
                        break
                if idx is None and ai.get_n_actions() > 0:
                    idx = 0
                if idx is None:
                    continue
                ok = ai.do_action(idx)
                activated = bool(ok) or activated
            except Exception as e:
                errors.append(str(e))
    if activated:
        return None
    if errors:
        return "AT-SPI activate errors: " + "; ".join(errors[:3])
    return f"no AT-SPI frame found for {app_id}"


def perform(step: dict[str, Any], *, raise_only: bool = False) -> dict[str, Any]:
    """Dispatch GuiStep. Returns actuation info dict with optional error."""
    stype = step.get("type")
    if stype == "FocusWindow":
        return _perform_focus(step, raise_only=raise_only)
    if stype == "TypeText":
        return _perform_type(step)
    if stype == "ClickA11y":
        return _perform_click_a11y(step)
    if stype == "Hotkey":
        return _perform_hotkey(step)
    return {
        "error": f"unsupported step type: {stype}",
        "frames_before": 0,
        "frames_after": 0,
    }


def _perform_type(step: dict[str, Any]) -> dict[str, Any]:
    from . import ydo

    text = step.get("text")
    if text is None or text == "":
        return {"error": "TypeText missing text", "method": "type"}
    submit = bool(step.get("submit"))
    foc = a11y.type_target()
    if not foc:
        return {
            "error": "no typeable target (focus a terminal/editor first)",
            "method": "type",
            "focused": None,
        }
    err = ydo.type_text(str(text))
    if err:
        return {"error": err, "method": "type", "focused": foc}
    if submit:
        time.sleep(0.08)
        enter_err = ydo.key_enter()
        if enter_err:
            return {"error": enter_err, "method": "type+enter", "focused": foc, "typed": True}
    return {
        "error": None,
        "method": "type+enter" if submit else "type",
        "focused": {k: v for k, v in foc.items() if k != "_obj"},
        "typed": True,
        "submit": submit,
        "text_len": len(str(text)),
    }




def _perform_hotkey(step: dict[str, Any]) -> dict[str, Any]:
    from . import ydo

    keys = step.get("keys")
    if not isinstance(keys, list):
        return {"error": "Hotkey keys must be a list", "method": "hotkey"}

    obs = a11y.observe()
    require_app = step.get("app_id") or step.get("require_app")
    # Prefer ACTIVE client frame (gnome-shell often steals FOCUSED in observe()).
    active = None
    for fr in obs.get("frames") or []:
        flags = fr.get("flags") or []
        app = str(fr.get("app_id") or "")
        if "ACTIVE" not in flags:
            continue
        if app.lower() == "gnome-shell":
            continue
        active = fr
        break

    if require_app:
        if not active or not a11y.app_match(str(active.get("app_id") or ""), str(require_app)):
            got = (active or {}).get("app_id") or (obs.get("focused") or {}).get("app_id")
            return {
                "error": (
                    f"Hotkey requires ACTIVE {require_app}; "
                    f"got {got!r}. Focus the target app first."
                ),
                "method": "hotkey",
                "keys": keys,
                "focused_before": active or obs.get("focused"),
            }
    elif not active:
        return {
            "error": "no ACTIVE client application for Hotkey",
            "method": "hotkey",
            "keys": keys,
            "focused_before": obs.get("focused"),
        }

    err = ydo.hotkey(keys)
    return {
        "error": err,
        "method": "ydotool_key",
        "keys": keys,
        "focused_before": active or obs.get("focused"),
        "require_app": require_app,
    }


def _perform_click_a11y(step: dict[str, Any]) -> dict[str, Any]:
    from . import ydo

    role = str(step.get("role") or "")
    name = str(step.get("name") or "")
    hit = a11y.find_a11y_target(role=role, name=name, window=step.get("window"))
    if not hit:
        return {
            "error": f"ClickA11y target not found: role={role!r} name={name!r}",
            "method": "click_a11y",
        }
    obj = hit.get("_obj")
    method = "a11y_action"
    if obj is not None and a11y.try_a11y_click(obj):
        time.sleep(0.2)
        return {
            "error": None,
            "method": method,
            "target": {k: v for k, v in hit.items() if k != "_obj"},
        }
    # Fallback: absolute click (needs disabled mouse accel for accuracy).
    err = ydo.click_abs(int(hit["cx"]), int(hit["cy"]))
    if err:
        return {
            "error": err,
            "method": "ydotool_click",
            "target": {k: v for k, v in hit.items() if k != "_obj"},
        }
    return {
        "error": None,
        "method": "ydotool_click",
        "target": {k: v for k, v in hit.items() if k != "_obj"},
    }


def _perform_focus(step: dict[str, Any], *, raise_only: bool = False) -> dict[str, Any]:
    """Run FocusWindow. Returns {error, frames_before, frames_after, ...}.

    When frames already exist: Activate/AT-SPI, then **overview raise via ydotool**
    (no --new-window). Reject if frame count rises.

    raise_only=True: never launch/rebind; require frames already present
    (Silvio protocol: baseline must be stable before the run).
    """
    app_id = step.get("app_id")
    if not app_id:
        return {"error": "FocusWindow missing app_id", "frames_before": 0, "frames_after": 0}

    pre = a11y.observe()
    frames_before = target_frame_count(pre, app_id)

    tree_err = ensure_in_tree(app_id, allow_launch=not raise_only)
    if tree_err:
        post = a11y.observe()
        return {
            "error": tree_err,
            "frames_before": frames_before,
            "frames_after": target_frame_count(post, app_id),
            "raise_only": raise_only,
        }

    mid = a11y.observe()
    frames_mid = target_frame_count(mid, app_id)

    dbus_err = _activate_dbus(app_id)
    atspi_err = _activate_atspi(app_id)
    time.sleep(0.35)

    raise_err = None
    if not a11y.target_active(a11y.observe(), app_id):
        # Existing window(s): raise via Overview (ydotool), never --new-window.
        raise_err = raise_mod.raise_existing(app_id)

    post = a11y.observe()
    frames_after = target_frame_count(post, app_id)
    opened_extra = frames_after > frames_mid

    err = None
    if opened_extra:
        err = (
            f"FocusWindow opened extra frames for {app_id} "
            f"({frames_mid} → {frames_after}); treat as failure"
        )
    elif raise_err and not a11y.target_active(post, app_id):
        err = (
            f"raise-only failed for {app_id}: {raise_err} "
            f"(dbus={dbus_err}; atspi={atspi_err})"
        )
    elif dbus_err and atspi_err and raise_err is None and not a11y.target_active(post, app_id):
        err = f"dbus: {dbus_err}; atspi: {atspi_err}"

    return {
        "error": err,
        "frames_before": frames_before,
        "frames_after": frames_after,
        "frames_mid": frames_mid,
        "opened_extra": opened_extra,
        "dbus_err": dbus_err,
        "atspi_err": atspi_err,
        "raise_err": raise_err,
        "raise_only": raise_only,
        "method": "overview_ydotool"
        if raise_err is None and a11y.target_active(post, app_id)
        else "activate",
    }
