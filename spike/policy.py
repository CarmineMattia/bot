"""Tiny policy gate for the spike (docs/policy.md). Focus = auto."""

from __future__ import annotations

from typing import Any, Literal


Decision = Literal["auto", "ask", "deny"]


def decide(step: dict[str, Any]) -> Decision:
    t = step.get("type")
    if t == "FocusWindow":
        return "auto"
    if t in {"ClickA11y", "ClickPoint", "TypeText", "Hotkey"}:
        # not implemented in spike actuation yet — ask
        return "ask"
    return "deny"
