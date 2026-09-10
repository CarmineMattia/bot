"""Stub planner: map a few phrases to one GUI or code step."""

from __future__ import annotations

import re
from pathlib import Path
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
        ("text editor", "gnome text editor", "gedit", "editor"),
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
        {
            "type": "Hotkey",
            "keys": ["ctrl", "shift", "t"],
            "app_id": "org.gnome.Ptyxis",
        },
        "Open a new Ptyxis tab (Ctrl+Shift+T)",
    ),
]


def _wordish(haystack: str, needle: str) -> bool:
    """Match needle as whole words / phrase, not bare substring inside another word."""
    h = haystack.lower().strip()
    n = needle.lower().strip()
    if not n:
        return False
    if " " in n or "-" in n:
        return n in h
    return re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", h) is not None


def _parse_type(user_text: str) -> dict[str, Any] | None:
    t = user_text.strip()
    m = re.match(
        r"^(?:type|digita|scrivi)\s+(.+)$",
        t,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    rest = m.group(1).strip()
    submit = False
    for cue in (
        " and press enter",
        " then enter",
        " and enter",
        " + enter",
        " con invio",
        " e invio",
        " and submit",
        " then submit",
        " + submit",
        " submit",
    ):
        if rest.lower().endswith(cue):
            rest = rest[: -len(cue)].strip()
            submit = True
            break
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
        if any(_wordish(low, k) for k in keys):
            return dict(step)
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
    # Hotkey before Focus: "new tab" must not fall through to nothing / wrong hand.
    for keys, step, _announce in KNOWN_HOTKEY:
        if any(t == key or _wordish(t, key) for key in keys):
            return dict(step)
    # Prefer "focus …" cues; still allow bare app names.
    for keys, step, _announce in KNOWN_FOCUS:
        if any(_wordish(t, k) for k in keys):
            return dict(step)
    return None



def plan_step(
    user_text: str,
    *,
    workspace: Path | None = None,
    last_observation: dict[str, Any] | None = None,
    action_log_tail: list[dict[str, Any]] | None = None,
    use_brain: bool | None = None,
) -> dict[str, Any] | None:
    """Plan exactly one spike step.

    Explicit ``code``/``omp`` prefixes always use the stub CodeTask path (deterministic
    tests + operator intent). Otherwise try the LLM brain when enabled; on failure
    fall back to GUI phrase stubs.
    """
    root = (workspace or Path.cwd()).expanduser().resolve()

    match = re.match(
        r"^(?:code|omp)\s+(.+)$",
        user_text.strip(),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        prompt = match.group(1).strip()
        if prompt:
            return {
                "type": "CodeTask",
                "prompt": prompt,
                "workspace": str(root),
            }

    if use_brain is None:
        from . import brain

        try_brain = brain.enabled()
    else:
        try_brain = use_brain

    if try_brain:
        from . import brain

        try:
            return brain.plan(
                user_text,
                workspace=root,
                last_observation=last_observation,
                action_log_tail=action_log_tail,
            )
        except brain.BrainError:
            pass

    return plan_gui_step(user_text)


def announce_for(step: dict[str, Any]) -> str:
    stype = step.get("type")
    if stype == "Talk":
        reply = str(step.get("reply") or "")
        shown = reply if len(reply) <= 80 else reply[:77] + "…"
        return f"Reply: {shown}"
    if stype == "CodeTask":
        prompt = str(step.get("prompt") or "")
        shown = prompt if len(prompt) <= 100 else prompt[:97] + "…"
        return f"Ask omp: {shown}"
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
