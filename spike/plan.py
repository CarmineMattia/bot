"""Stub planner: map a few phrases to GuiStep (docs/gui-loop.md)."""

from __future__ import annotations

from typing import Any


# app_id is freedesktop Application bus name / desktop id stem
KNOWN: list[tuple[tuple[str, ...], dict[str, Any], str]] = [
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


def plan_gui_step(user_text: str) -> dict[str, Any] | None:
    t = user_text.strip().lower()
    for keys, step, _announce in KNOWN:
        if any(k in t for k in keys):
            return dict(step)
    return None


def announce_for(step: dict[str, Any]) -> str:
    for _keys, known, announce in KNOWN:
        if known.get("app_id") == step.get("app_id") and known.get("type") == step.get("type"):
            return announce
    return f"Perform {step.get('type')}"
