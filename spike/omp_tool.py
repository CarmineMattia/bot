"""Single-shot oh-my-pi CLI adapter for the conductor spike."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

MAX_OUTPUT_CHARS = 1_000_000
ENV_NAMES = {
    "COLORTERM",
    "HOME",
    "LANG",
    "LANGUAGE",
    "LOGNAME",
    "NO_COLOR",
    "PATH",
    "SHELL",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "TERM",
    "TMPDIR",
    "USER",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
}
ENV_PREFIXES = (
    "ANTHROPIC_",
    "AZURE_OPENAI_",
    "GEMINI_",
    "GOOGLE_GENERATIVE_AI_",
    "OMP_",
    "OPENAI_",
    "PI_",
    "XAI_",
)


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


def _subprocess_env() -> dict[str, str]:
    """Pass runtime essentials and model-provider settings, not unrelated tokens."""
    return {
        name: value
        for name, value in os.environ.items()
        if name in ENV_NAMES or name.startswith(ENV_PREFIXES)
    }


def _parse_jsonl(stdout: str) -> list[Any] | None:
    events: list[Any] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            return None
    return events or None


def _assistant_response(events: list[Any]) -> str | None:
    """Extract the last assistant text when omp emits its JSONL event stream."""
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            chunks = [
                str(part.get("text"))
                for part in content
                if isinstance(part, dict)
                and part.get("type") == "text"
                and part.get("text")
            ]
            if chunks:
                return "\n".join(chunks).strip()
    return None


def run_task(prompt: str, workspace: Path, *, timeout_s: float = 900.0) -> dict[str, Any]:
    """Run one non-interactive omp task and wait for its result.

    JSON mode is a stable JSONL event stream in current omp releases. If an
    older installation emits non-JSON output, preserve it as text without
    launching a second omp process.
    """
    prompt = prompt.strip()
    root = workspace.expanduser().resolve()
    if not prompt:
        return {"error": "CodeTask prompt is empty", "method": "omp"}
    if not root.is_dir():
        return {
            "error": f"CodeTask workspace is not a directory: {root}",
            "method": "omp",
        }
    if not (root / ".git").exists():
        return {
            "error": f"CodeTask workspace is not a repository root: {root}",
            "method": "omp",
        }

    executable = shutil.which("omp")
    if executable is None:
        return {
            "error": "omp executable not found on PATH",
            "method": "omp",
            "workspace": str(root),
        }
    sandbox = shutil.which("bwrap")
    if sandbox is None:
        return {
            "error": "bwrap executable required to contain omp workspace writes",
            "method": "omp",
            "workspace": str(root),
        }

    command = [
        sandbox,
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--ro-bind",
        "/",
        "/",
        "--bind",
        str(root),
        str(root),
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--chdir",
        str(root),
        executable,
        "--cwd",
        str(root),
        "--mode",
        "json",
        "--approval-mode",
        "write",
        "--no-session",
        "--no-extensions",
        "--no-skills",
        "--no-rules",
        "--no-lsp",
        "--tools",
        "read,grep,find,ls,edit,write",
        "--print",
        prompt,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=_subprocess_env(),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "error": f"omp timed out after {timeout_s:g}s",
            "method": "omp_print_json",
            "workspace": str(root),
            "timeout_s": timeout_s,
            "stdout": _text(exc.stdout),
            "stderr": _text(exc.stderr),
        }
    except OSError as exc:
        return {
            "error": f"failed to start omp: {exc}",
            "method": "omp_print_json",
            "workspace": str(root),
        }

    stdout = _text(completed.stdout)[:MAX_OUTPUT_CHARS]
    stderr = _text(completed.stderr)[:MAX_OUTPUT_CHARS]
    events = _parse_jsonl(stdout)
    if events is None:
        output_format = "text_fallback"
        response = stdout.strip() or None
    else:
        output_format = "jsonl"
        response = _assistant_response(events)

    error = None
    if completed.returncode != 0:
        error = f"omp exited with status {completed.returncode}"

    result: dict[str, Any] = {
        "error": error,
        "method": "omp_print_json",
        "workspace": str(root),
        "returncode": completed.returncode,
        "format": output_format,
        "response": response,
        "stderr": stderr,
    }
    if events is None:
        result["stdout"] = stdout
    else:
        result["events"] = events
        result["event_count"] = len(events)
    return result