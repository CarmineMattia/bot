"""Stub planner: map a few phrases to GuiStep (docs/gui-loop.md)."""

from __future__ import annotations

import re
from typing import Any


# app_id is freedesktop Application bus name / desktop id stem
KNOWN_FOCUS: list[tuple[tuple[str, ...], dict[str, Any], str]] = [
    (
        ("terminal", "ptyxis", "console"),
        {"type": "FocusWindow", "app_id": "org.gnome.Ptyxis", "title_match": None},
        "Focus the terminal (Ptyxis)",
    ),
    (
        ("files", "nautilus", "file manager", "filemanager", "cartelle"),
        {"type": "FocusWindow", "app_id": "org.gnome.Nautilus", "title_match": None},
        "Focus Files (Nautilus)",
    ),
    (
        ("editor", "text editor", "gedit", "write"),
        {"type": "FocusWindow", "app_id": "org.gnome.TextEditor", "title_match": None},
        "Focus Text Editor",
    ),
]

# ClickA11y demos — role defaults to push button unless specified.
KNOWN_CLICK: list[tuple[tuple[str, ...], dict[str, Any], str]] = [
    (
        ("new tab", "new-tab"),
        {"type": "ClickA11y", "role": "push button", "name": "New Tab", "window": None},
        "Click New Tab",
    ),
    (
        ("new folder", "nuova cartella"),
        {"type": "ClickA11y", "role": "push button", "name": "New Folder", "window": None},
        "Click New Folder",
    ),
]

KNOWN_HOTKEY: list[tuple[tuple[str, ...], dict[str, Any], str]] = [
    (
        ("new tab", "open a new tab", "nuova scheda", "apri una nuova scheda"),
        {"type": "Hotkey", "keys": ["ctrl", "shift", "t"]},
        "Open a new Ptyxis tab (Ctrl+Shift+T)",
    ),
]



def _parse_type(user_text: str) -> dict[str, Any] | None:
    t = user_text.strip()
    low = t.lower()
    m = re.match(
        r"^(?:type|digita|scrivi)\s+(.+)$",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    rest = m.group(1).strip()
    submit = False
    # strip trailing submit cues
    for cue in (
        " and press enter",
        " then enter",
        " and enter",
        " + enter",
        " con invio",
        " e invio",
    ):
        if rest.lower().endswith(cue):
            rest = rest[: -len(cue)].strip()
            submit = True
            break
    if "submit" in low and not submit:
        # "type foo submit" / "type submit foo"
        rest2 = re.sub(r"\bsubmit\b", "", rest, flags=re.IGNORECASE).strip()
        if rest2 != rest:
            rest = rest2
            submit = True
    # quoted string
    qm = re.match(r'^["\'](.+)["\']\s*$', rest, flags=re.DOTALL)
    if qm:
        rest = qm.group(1)
    if not rest:
        return None
    return {"type": "TypeText", "text": rest, "submit": submit}


def _parse_click(user_text: str) -> dict[str, Any] | None:
    t = user_text.strip()
    m = re.match(
        r"^(?:click|clicca|premi)\s+(.+)$",
        t,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    rest = m.group(1).strip()
    low = rest.lower()
    for keys, step, _ann in KNOWN_CLICK:
        if any(k in low for k in keys):
            return dict(step)
    # generic: click <name>  (role = push button)
    # optional "button/menu ..."
    role = "push button"
    name = rest
    rm = re.match(
        r"^(?:button|menu item|menu|tab|toggle)\s+(.+)$",
        rest,
        flags=re.IGNORECASE,
    )
    if rm:
        kind = rest[: len(rest) - len(rm.group(1))].strip().lower()
        name = rm.group(1).strip()
        role = {
            "button": "push button",
            "menu item": "menu item",
            "menu": "menu",
            "tab": "page tab",
            "toggle": "toggle button",
        }.get(kind, "push button")
    if not name:
        return None
    return {"type": "ClickA11y", "role": role, "name": name, "window": None}


def plan_gui_step(user_text: str) -> dict[str, Any] | None:
    typed = _parse_type(user_text)
    if typed:
        return typed
    clicked = _parse_click(user_text)
    if clicked:
        return clicked
    t = user_text.strip().lower()
    for keys, step, _announce in KNOWN_HOTKEY:
        if any(t == key for key in keys):
            return dict(step)
    for keys, step, _announce in KNOWN_FOCUS:
        if any(k in t for k in keys):
            return dict(step)
    return None


def announce_for(step: dict[str, Any]) -> str:
    stype = step.get("type")
    if stype == "TypeText":
        text = str(step.get("text") or "")
        shown = text if len(text) <= 40 else text[:37] + "…"
        suffix = " + Enter" if step.get("submit") else ""
        return f"Type {shown!r}{suffix}"
    if stype == "ClickA11y":
        for _keys, known, announce in KNOWN_CLICK:
            if known.get("name") == step.get("name") and known.get("role") == step.get("role"):
                return announce
        return f"Click {step.get('role')} {step.get('name')!r}"
    if stype == "Hotkey":
        for _phrases, known, announce in KNOWN_HOTKEY:
            if known.get("keys") == step.get("keys"):
                return announce
        return "Press " + "+".join(str(k) for k in (step.get("keys") or []))
    for _keys, known, announce in KNOWN_FOCUS:
        if known.get("app_id") == step.get("app_id") and known.get("type") == stype:
            return announce
    return f"Perform {stype}"
