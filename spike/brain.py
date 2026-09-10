"""Conductor brain: one-shot classify + plan via OpenAI-compatible HTTP.

Talks to llama.cpp (`llama-server`) or Ollama `/v1`. Falls back to the stub
planner when disabled or unreachable (docs/adapters.md).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ALLOWED_FOCUS_APPS = {
    "org.gnome.Ptyxis",
    "org.gnome.Nautilus",
    "org.gnome.TextEditor",
}

ALLOWED_HOTKEYS = {
    ("ctrl", "shift", "t"),
}

DANGEROUS_TYPE_TEXT_RE = re.compile(
    r"(?<![\w-])(?:sudo|rm|passwd|curl|wget|ssh|scp|chmod|chown|dd|"
    r"mkfs(?:\.[a-z0-9]+)?|shutdown|reboot)(?![\w-])",
    flags=re.IGNORECASE,
)

CONFIRM_CLICK_NAMES = (
    "ok",
    "yes",
    "accept",
    "continue",
    "sign in",
    "cancel",
)

SYSTEM_PROMPT = """You are the planning brain for a local desktop conductor (bot).
Return ONLY one JSON object (no markdown fences, no commentary).

Schema:
{
  "classify": "talk" | "code" | "gui",
  "step": null | GuiStep | CodeTask | Talk,
  "reply": string | null
}

Rules:
- Exactly ONE step this turn. Never invent a multi-step plan.
- talk: side-effect free answer → {"type":"Talk","reply":"..."} (short).
- code: repo/edit/test work → {"type":"CodeTask","prompt":"..."} (no workspace field).
- gui: desktop gesture only, one of:
  FocusWindow { "type":"FocusWindow", "app_id": one of
    "org.gnome.Ptyxis", "org.gnome.Nautilus", "org.gnome.TextEditor" }
  TypeText { "type":"TypeText", "text":"...", "submit": false|true }
  ClickA11y { "type":"ClickA11y", "role":"push button", "name":"..." }
  Hotkey { "type":"Hotkey", "keys":["ctrl","shift","t"], "app_id":"org.gnome.Ptyxis" }
- Prefer FocusWindow over guessing clicks. Prefer Hotkey new tab over ClickA11y New Tab.
- If ambiguous between code and gui, prefer the clearer one; if still unclear, talk and ask.
- Do not include secrets, sudo, or destructive shell in TypeText submit.
- Dangerous command text and confirmation-style buttons are preserved but require
  explicit operator confirmation by the policy layer.
"""


class BrainError(Exception):
    """Brain unavailable or returned an invalid plan."""


def enabled() -> bool:
    # Default off: stub planner stays deterministic unless operator opts in.
    return os.environ.get("BOT_BRAIN", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "auto",
    }


def base_url() -> str:
    return os.environ.get("BOT_LLM_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")


def model_name() -> str:
    return os.environ.get("BOT_LLM_MODEL", "default")


def _chat(messages: list[dict[str, str]], *, timeout_s: float) -> str:
    url = f"{base_url()}/chat/completions"
    payload = {
        "model": model_name(),
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 400,
    }
    # Ollama + many llama.cpp builds honor this; ignore if unsupported.
    payload["response_format"] = {"type": "json_object"}

    def request(current_payload: dict[str, Any]) -> Any:
        req = urllib.request.Request(
            url,
            data=json.dumps(current_payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode())

    try:
        try:
            body = request(payload)
        except urllib.error.HTTPError as first_error:
            # Retry without response_format if server rejects it.
            if first_error.code not in {400, 422}:
                raise
            payload.pop("response_format", None)
            body = request(payload)
    except urllib.error.HTTPError as e:
        try:
            detail = e.read()[:200]
        except Exception:
            detail = b"<unavailable>"
        raise BrainError(f"LLM HTTP {e.code}: {detail!r}") from e
    except Exception as e:
        raise BrainError(f"LLM unreachable at {url}: {e}") from e

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise BrainError(f"unexpected LLM response shape: {body!r}") from e
    if not isinstance(content, str) or not content.strip():
        raise BrainError("empty LLM content")
    return content.strip()


def _extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not m:
            raise BrainError(f"no JSON object in model output: {text[:200]!r}")
        obj = json.loads(m.group(0))
    if not isinstance(obj, dict):
        raise BrainError("model JSON root must be an object")
    return obj


def validate_step(
    step: dict[str, Any] | None,
    *,
    classify: str,
    workspace: Path,
) -> dict[str, Any] | None:
    """Return a normalized step or raise BrainError."""
    if classify == "talk":
        if not step or step.get("type") != "Talk":
            reply = ""
            if isinstance(step, dict):
                reply = str(step.get("reply") or "")
            if not reply:
                raise BrainError("talk classify requires Talk.reply")
            step = {"type": "Talk", "reply": reply}
        reply = str(step.get("reply") or "").strip()
        if not reply:
            raise BrainError("Talk.reply empty")
        return {"type": "Talk", "reply": reply[:2000]}

    if not isinstance(step, dict) or not step.get("type"):
        raise BrainError(f"{classify} classify requires a step object")

    stype = step.get("type")
    if classify == "code":
        if stype != "CodeTask":
            raise BrainError("code classify requires CodeTask")
        prompt = str(step.get("prompt") or "").strip()
        if not prompt:
            raise BrainError("CodeTask.prompt empty")
        return {
            "type": "CodeTask",
            "prompt": prompt,
            "workspace": str(workspace.expanduser().resolve()),
        }

    if classify != "gui":
        raise BrainError(f"unknown classify: {classify!r}")

    if stype == "FocusWindow":
        app_id = str(step.get("app_id") or "")
        if app_id not in ALLOWED_FOCUS_APPS:
            raise BrainError(f"FocusWindow app_id not allowlisted: {app_id!r}")
        return {"type": "FocusWindow", "app_id": app_id, "title_match": None}

    if stype == "TypeText":
        text = str(step.get("text") or "")
        if not text:
            raise BrainError("TypeText.text empty")
        normalized = {
            "type": "TypeText",
            "text": text[:500],
            "submit": bool(step.get("submit")),
        }
        if DANGEROUS_TYPE_TEXT_RE.search(text):
            normalized["requires_confirmation"] = True
        return normalized

    if stype == "ClickA11y":
        role = str(step.get("role") or "push button")
        name = str(step.get("name") or "").strip()
        if not name:
            raise BrainError("ClickA11y.name empty")
        normalized = {
            "type": "ClickA11y",
            "role": role,
            "name": name[:120],
            "window": step.get("window"),
        }
        canonical_name = re.sub(r"\s+", " ", name.casefold())
        if any(
            re.search(rf"(?<!\w){re.escape(hint)}(?!\w)", canonical_name)
            for hint in CONFIRM_CLICK_NAMES
        ):
            normalized["requires_confirmation"] = True
        return normalized

    if stype == "Hotkey":
        keys = tuple(str(k).lower() for k in (step.get("keys") or []))
        if keys not in ALLOWED_HOTKEYS:
            raise BrainError(f"Hotkey not allowlisted: {keys}")
        app_id = str(step.get("app_id") or "org.gnome.Ptyxis")
        if app_id not in ALLOWED_FOCUS_APPS:
            raise BrainError(f"Hotkey app_id not allowlisted: {app_id!r}")
        return {"type": "Hotkey", "keys": list(keys), "app_id": app_id}

    if stype == "ClickPoint":
        raise BrainError("ClickPoint not allowed from brain in spike v1")

    raise BrainError(f"unsupported step type from brain: {stype!r}")


def plan(
    user_text: str,
    *,
    workspace: Path,
    last_observation: dict[str, Any] | None = None,
    action_log_tail: list[dict[str, Any]] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Call the LLM and return a validated step dict (includes Talk / CodeTask / GUI)."""
    if not enabled():
        raise BrainError("brain disabled")

    timeout_s = float(timeout_s or os.environ.get("BOT_LLM_TIMEOUT", "45"))
    context_bits = {
        "user_text": user_text,
        "workspace": str(workspace),
        "last_observation_summary": (last_observation or {}).get("summary"),
        "recent_actions": action_log_tail or [],
    }
    content = _chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(context_bits, ensure_ascii=False),
            },
        ],
        timeout_s=timeout_s,
    )
    obj = _extract_json(content)
    classify = str(obj.get("classify") or "").strip().lower()
    step_raw = obj.get("step")
    if step_raw is None and classify == "talk" and obj.get("reply"):
        step_raw = {"type": "Talk", "reply": obj.get("reply")}
    return validate_step(step_raw, classify=classify, workspace=workspace)
