"""Tiny policy gate for the spike (docs/policy.md)."""

from __future__ import annotations

import re
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
    "cancel",
    "save",
    "apply",
    "discard",
    "overwrite",
    "replace",
    "quit",
    "exit",
    # Dialog affirmatives can commit or dismiss state even when their labels are
    # generic. Keep obviously navigational demo targets (for example New Tab)
    # automatic, but require confirmation for these affirmative verbs.
    "accept",
    "continue",
    "proceed",
    "agree",
    "approve",
    "authorize",
    "sign in",
    "signin",
    "log in",
    "login",
    "got it",
)

ASK_EXACT_NAMES = {
    "ok",
    "okay",
    "yes",
    "done",
    "close",
    "dismiss",
    "cancel",
    "save",
    "don't save",
    "dont save",
    "do not save",
    "apply",
    "discard",
    "overwrite",
    "replace",
    "quit",
    "exit",
}

DANGEROUS_TEXT_RE = re.compile(
    r"(?<![\w-])(?:sudo|rm|passwd|curl|wget|ssh|scp|chmod|chown|dd|"
    r"mkfs(?:\.[a-z0-9]+)?|shutdown|reboot)(?![\w-])",
    re.IGNORECASE,
)
SHELL_EVALUATION_RE = re.compile(r"\$\{|\$\(|`")


def _normalized_name(name: Any) -> str:
    return " ".join(
        str(name or "").lower().replace("-", " ").replace("’", "'").split()
    )


def _dangerous_typed_text(text: Any) -> bool:
    # Shell concatenates quoted and backslash-escaped token fragments, so scan a
    # dequoted form too (for example cu''rl or c$''url). Parameter/command
    # expansion is itself gated because it can reconstruct or execute a command
    # that is not statically visible here.
    raw = str(text or "")
    dequoted = re.sub(r"""['"\\$]""", "", raw)
    return bool(
        SHELL_EVALUATION_RE.search(raw)
        or DANGEROUS_TEXT_RE.search(raw)
        or DANGEROUS_TEXT_RE.search(dequoted)
    )


def decide(step: dict[str, Any]) -> Decision:
    if step.get("requires_confirmation"):
        return "ask"

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
        # Staging a dangerous command is itself sensitive: the user (or another
        # turn) can submit it later, so submit=False must not bypass policy.
        if _dangerous_typed_text(step.get("text")):
            return "ask"
        return "auto"
    if t == "ClickA11y":
        name = _normalized_name(step.get("name"))
        if name in ASK_EXACT_NAMES or any(h in name for h in ASK_NAME_HINTS):
            return "ask"
        return "auto"
    if t == "Hotkey":
        keys = tuple(str(key).lower() for key in step.get("keys") or [])
        return "auto" if keys in AUTO_HOTKEYS else "ask"
    if t == "ClickPoint":
        return "ask"
    return "deny"
