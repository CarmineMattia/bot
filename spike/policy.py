"""Tiny policy gate for the spike (docs/policy.md)."""

from __future__ import annotations

from typing import Any, Literal


Decision = Literal["auto", "ask", "deny"]

AUTO_HOTKEYS = {
    ("ctrl", "shift", "t"),  # Ptyxis: open a reversible new tab
}

# Names that imply irreversible / external actions → ask even for ClickA11y.
ASK_NAME_HINTS = (
    "delete",
    "remove",
    "trash",
    "empty",
    "buy",
    "purchase",
    "pay",
    "send",
    "submit",
    "confirm",
    "install",
    "uninstall",
    "format",
    "shutdown",
    "reboot",
    "allow",
    "grant",
    "password",
)


def decide(step: dict[str, Any]) -> Decision:
    t = step.get("type")
    if t == "Talk":
        return "auto"
    if t == "CodeTask":
        # omp has no path-scoped read sandbox. Keep every delegated task behind
        # explicit conductor confirmation rather than trusting prompt wording.
        return "ask"
    if t == "FocusWindow":
        return "auto"
    if t == "TypeText":
        text = str(step.get("text") or "").lower()
        if step.get("submit") and any(h in text for h in ("rm ", "sudo", "passwd", "curl ")):
            return "ask"
        return "auto"
    if t == "ClickA11y":
        name = str(step.get("name") or "").lower()
        if any(h in name for h in ASK_NAME_HINTS):
            return "ask"
        return "auto"
    if t == "Hotkey":
        keys = tuple(str(key).lower() for key in step.get("keys") or [])
        return "auto" if keys in AUTO_HOTKEYS else "ask"
    if t == "ClickPoint":
        return "ask"
    return "deny"
