"""Minimal GUI-loop spike for Linux (GNOME/Wayland first).

Implements docs/gui-loop.md success criteria with:
- stub planner (no LLM): FocusWindow | TypeText | ClickA11y | Hotkey | CodeTask
- overlay (GTK UI + stderr log; BOT_OVERLAY=0 disables UI)
- FocusWindow: ensure target in AT-SPI tree, then Activate / overview raise
- TypeText / ClickA11y: ydotool (+ AT-SPI action when possible)
- Hotkey: explicit ydotool key chord (no ClickA11y fallback)
- CodeTask: one non-interactive omp invocation in the repository workspace
- FocusWindow observe requires an ACTIVE *transition* (Silvio: already-focused ≠ proof)
- Soft-fail: retry same step once when observe shows no meaningful delta

Run from a normal user session (Ptyxis):

    python3 -m spike "focus files"
    python3 -m spike "focus the terminal"
    python3 -m spike "type echo bot-ok"
    python3 -m spike "click New Tab"
    python3 -m spike "new tab"
    python3 -m spike "code explain README.md"
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from . import a11y, act, confirm, omp_tool, overlay, plan, policy

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".spike_state.json"

Outcome = Literal[
    "ok",
    "retry",
    "stop",
    "already_focused",
    "need_confirm",
    "cancelled",
]


@dataclass
class ActionEntry:
    t: str
    announce: str
    step: dict[str, Any]
    policy_decision: str
    outcome: str
    observation_summary: str


@dataclass
class SpikeState:
    action_log: list[ActionEntry] = field(default_factory=list)
    last_observation: dict[str, Any] | None = None

    def trim(self, n: int = 20) -> None:
        self.action_log = self.action_log[-n:]


def load_state() -> SpikeState:
    if not STATE_PATH.exists():
        return SpikeState()
    raw = json.loads(STATE_PATH.read_text())
    log = [ActionEntry(**e) for e in raw.get("action_log", [])]
    return SpikeState(action_log=log, last_observation=raw.get("last_observation"))


def save_state(state: SpikeState) -> None:
    state.trim()
    STATE_PATH.write_text(
        json.dumps(
            {
                "action_log": [asdict(e) for e in state.action_log],
                "last_observation": state.last_observation,
            },
            indent=2,
        )
        + "\n"
    )


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _with_changed(obs: dict[str, Any] | None, changed: bool) -> dict[str, Any] | None:
    if obs is None:
        return None
    out = dict(obs)
    out["changed"] = bool(changed)
    return out


def _emit(
    state: SpikeState,
    *,
    announce: str,
    step: dict[str, Any] | None,
    decision: str,
    outcome: str,
    reply: str,
    observation: dict[str, Any] | None,
    changed: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append action log (every exit), persist, print JSON result."""
    obs = _with_changed(observation, changed)
    entry = ActionEntry(
        t=iso_now(),
        announce=announce,
        step=step or {},
        policy_decision=decision,
        outcome=outcome,
        observation_summary=str((obs or {}).get("summary") or ""),
    )
    state.action_log.append(entry)
    if obs is not None:
        state.last_observation = obs
    save_state(state)
    result: dict[str, Any] = {
        "announce": announce,
        "step": step,
        "policy": decision,
        "outcome": outcome,
        "observation": obs,
        "user_reply": reply,
        "action_log_len": len(state.action_log),
    }
    if extra:
        result.update(extra)
    print(json.dumps(result, indent=2))
    return result


def _retry_same(
    step: dict[str, Any],
    *,
    announce: str,
    pause_ms: int,
    raise_only: bool,
    pre: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """One soft-fail retry of the same GuiStep. Returns (act_info, post)."""
    overlay.show(
        {
            "status": f"retry: {announce}",
            "phase": "announce",
            "target": a11y.target_hint_for_step(step),
        }
    )
    time.sleep(pause_ms / 1000.0)
    overlay.show(
        {
            "status": f"retry: {announce}",
            "phase": "acting",
            "target": a11y.target_hint_for_step(step),
        }
    )
    act_info = act.perform(step, raise_only=raise_only)
    time.sleep(0.45)
    post = a11y.observe()
    # keep pre for delta vs original pre-act snapshot (gui-loop: same step)
    _ = pre
    return act_info, post



def _run_code_task(
    *,
    step: dict[str, Any],
    announce: str,
    decision: str,
    state: SpikeState,
    pause_ms: int,
    raise_only: bool,
    user_confirm: str | None,
) -> dict[str, Any]:
    """Announce and execute exactly one omp process."""
    overlay.show({"status": announce, "phase": "announce", "pause_ms": pause_ms})
    if confirm.abortable_pause(pause_ms):
        reply = f"Aborted during announce pause: {announce}"
        overlay.show({"status": reply, "phase": "cancelled"})
        overlay.clear("cancelled")
        result = {
            "announce": announce,
            "step": step,
            "policy": decision,
            "outcome": "cancelled",
            "observation": None,
            "user_reply": reply,
            "user_confirm": "abort",
        }
        print(json.dumps(result, indent=2))
        return result

    overlay.show({"status": announce, "phase": "acting"})
    act_info = omp_tool.run_task(
        str(step.get("prompt") or ""),
        Path(str(step.get("workspace") or ROOT)),
    )
    act_err = act_info.get("error")
    response = str(act_info.get("response") or "").strip()
    if act_err:
        outcome = "stop"
        reply = f"omp failed: {act_err}"
        summary = reply
        phase = "failed"
    else:
        outcome = "ok"
        reply = response or "omp completed the delegated task."
        summary = (
            f"omp completed successfully "
            f"(format={act_info.get('format')}, events={act_info.get('event_count', 0)})"
        )
        phase = "done"

    overlay.show({"status": "done" if outcome == "ok" else reply, "phase": phase})
    overlay.clear(phase)
    observation = {
        "source": "omp",
        "summary": summary[:500],
        "changed": outcome == "ok",
    }
    state.action_log.append(
        ActionEntry(
            t=iso_now(),
            announce="Ask omp: <prompt omitted from persistent log>",
            step={
                "type": "CodeTask",
                "workspace": step.get("workspace"),
                "prompt": "<omitted from persistent log>",
                "prompt_chars": len(str(step.get("prompt") or "")),
            },
            policy_decision=decision,
            outcome=outcome,
            observation_summary=observation["summary"],
        )
    )
    state.last_observation = observation
    save_state(state)

    result = {
        "announce": announce,
        "step": step,
        "policy": decision,
        "outcome": outcome,
        "observation": observation,
        "user_reply": reply,
        "action_log_len": len(state.action_log),
        "transition": False,
        "frames_before": None,
        "frames_after": None,
        "opened_extra": False,
        "method": act_info.get("method"),
        "raise_err": None,
        "raise_only": raise_only,
        "user_confirm": user_confirm,
        "act": {k: v for k, v in act_info.items() if k != "error" or act_err},
    }
    print(json.dumps(result, indent=2))
    return result


def run_turn(
    user_text: str,
    pause_ms: int = 400,
    *,
    raise_only: bool = False,
    confirm_forced: str | None = None,
    confirm_timeout_s: float = 60.0,
) -> dict[str, Any]:
    state = load_state()
    step = plan.plan_step(user_text, workspace=ROOT)
    if step is None:
        return _emit(
            state,
            announce="",
            step=None,
            decision="deny",
            outcome="stop",
            reply=(
                "Stub planner does not understand: "
                f"{user_text!r}. Try: focus terminal | focus files | "
                "type hello | type hello and enter | click New Tab | new tab | code explain README.md"
            ),
            observation=state.last_observation,
            extra={},
        )

    decision = policy.decide(step)
    announce = plan.announce_for(step)
    stype = step.get("type")
    user_confirm: str | None = None

    if decision == "deny":
        return _emit(
            state,
            announce=announce,
            step=step,
            decision=decision,
            outcome="stop",
            reply=f"Denied by policy: {announce}",
            observation=None,
            extra={"user_confirm": None},
        )

    if decision == "ask":
        overlay.show(
            {
                "status": f"CONFIRM? {announce}  [y/n]",
                "phase": "announce",
                "target": a11y.target_hint_for_step(step),
            }
        )
        verdict = confirm.wait_confirm(
            prompt=f"Policy ask — confirm before act: {announce}",
            forced=confirm_forced,
            timeout_s=confirm_timeout_s,
        )
        user_confirm = verdict
        if verdict != "confirm":
            if verdict == "need_tty":
                outcome: Outcome = "need_confirm"
                reply = (
                    f"Confirm required before: {announce}. "
                    "Re-run with --yes / --no, or set BOT_CONFIRM=yes|no, or use a TTY."
                )
            elif verdict == "timeout":
                outcome = "cancelled"
                reply = f"Confirm timed out — aborted: {announce}"
            else:
                outcome = "cancelled"
                reply = f"Aborted by user before act: {announce}"
            overlay.show({"status": reply, "phase": "cancelled"})
            overlay.clear("cancelled")
            return _emit(
                state,
                announce=announce,
                step=step,
                decision=decision,
                outcome=outcome,
                reply=reply,
                observation=None,
                extra={"user_confirm": user_confirm},
            )
        overlay.show(
            {
                "status": announce,
                "phase": "announce",
                "target": a11y.target_hint_for_step(step),
            }
        )

    if stype == "CodeTask":
        return _run_code_task(
            step=step,
            announce=announce,
            decision=decision,
            state=state,
            pause_ms=pause_ms,
            raise_only=raise_only,
            user_confirm=user_confirm,
        )

    pre = a11y.observe()

    if stype == "FocusWindow":
        if a11y.already_focused(pre, step):
            reply = (
                f"Inconclusive: target already ACTIVE before act "
                f"({pre.get('summary')}). Switch to another window first, then retry."
            )
            overlay.show({"status": reply, "phase": "cancelled"})
            overlay.clear("cancelled")
            return _emit(
                state,
                announce=announce,
                step=step,
                decision=decision,
                outcome="already_focused",
                reply=reply,
                observation=pre,
                changed=False,
                extra={
                    "raise_only": raise_only,
                    "user_confirm": user_confirm,
                },
            )

        if raise_only and not a11y.target_in_tree(pre, step.get("app_id") or ""):
            reply = (
                f"raise-only: {step.get('app_id')} not in AT-SPI tree. "
                "Open exactly one window manually before the monitor starts."
            )
            overlay.show({"status": reply, "phase": "failed"})
            overlay.clear("failed")
            return _emit(
                state,
                announce=announce,
                step=step,
                decision=decision,
                outcome="stop",
                reply=reply,
                observation=pre,
                extra={
                    "frames_before": 0,
                    "frames_after": 0,
                    "opened_extra": False,
                    "raise_only": True,
                    "user_confirm": user_confirm,
                },
            )

    overlay.show(
        {
            "status": announce,
            "phase": "announce",
            "pause_ms": pause_ms,
            "target": a11y.target_hint_for_step(step),
        }
    )
    if confirm.abortable_pause(pause_ms):
        reply = f"Aborted during announce pause: {announce}"
        overlay.show({"status": reply, "phase": "cancelled"})
        overlay.clear("cancelled")
        return _emit(
            state,
            announce=announce,
            step=step,
            decision=decision,
            outcome="cancelled",
            reply=reply,
            observation=pre,
            extra={"user_confirm": "abort"},
        )

    overlay.show(
        {
            "status": announce,
            "phase": "acting",
            "target": a11y.target_hint_for_step(step),
        }
    )
    act_info = act.perform(step, raise_only=raise_only)
    act_err = act_info.get("error")
    time.sleep(0.45)
    post = a11y.observe()

    transition = False
    opened_extra = bool(act_info.get("opened_extra"))
    retried = False
    reply = ""
    outcome: Outcome = "stop"

    if stype == "FocusWindow":
        transition = a11y.changed(pre, post, step) and not opened_extra
        if act_err and not transition:
            outcome = "stop"
            reply = f"Act failed: {act_err}"
            overlay.show({"status": reply, "phase": "failed"})
        elif opened_extra:
            outcome = "stop"
            reply = (
                f"Rejected: FocusWindow must not open windows "
                f"(frames {act_info.get('frames_mid')}→{act_info.get('frames_after')}). "
                "Silvio: raise-only, no launch."
            )
            overlay.show({"status": "failed", "phase": "failed"})
        elif transition:
            outcome = "ok"
            reply = (
                f"Done (ACTIVE transition, frames={act_info.get('frames_after')}). "
                f"Focus now: {post.get('summary')}"
            )
            overlay.show({"status": "done", "phase": "done"})
        else:
            retried = True
            act_info, post = _retry_same(
                step, announce=announce, pause_ms=pause_ms, raise_only=raise_only, pre=pre
            )
            act_err = act_info.get("error")
            opened_extra = bool(act_info.get("opened_extra"))
            transition = a11y.changed(pre, post, step) and not opened_extra
            if transition and not opened_extra:
                outcome = "ok"
                reply = (
                    f"Done after retry (ACTIVE transition, frames={act_info.get('frames_after')}). "
                    f"Focus now: {post.get('summary')}"
                )
                overlay.show({"status": "done", "phase": "done"})
            else:
                outcome = "stop"
                reply = (
                    "No raise-only ACTIVE transition after act/retry. "
                    f"pre={pre.get('summary')!r} post={post.get('summary')!r} "
                    f"frames {act_info.get('frames_before')}→{act_info.get('frames_after')} "
                    f"opened_extra={opened_extra}."
                )
                overlay.show({"status": "failed", "phase": "failed"})

    elif stype == "TypeText":
        # Ptyxis rarely exposes typed text in AT-SPI; trust type_target + ydotool.
        # Still soft-retry once on actuation error.
        if act_err:
            retried = True
            act_info, post = _retry_same(
                step, announce=announce, pause_ms=pause_ms, raise_only=raise_only, pre=pre
            )
            act_err = act_info.get("error")
        if act_err:
            outcome = "stop"
            reply = f"TypeText failed: {act_err}"
            overlay.show({"status": reply, "phase": "failed"})
        else:
            transition = a11y.fingerprint_delta(pre, post)
            outcome = "ok"
            foc = act_info.get("focused") or {}
            reply = (
                f"Typed {act_info.get('text_len', 0)} chars"
                f"{' + Enter' if step.get('submit') else ''} "
                f"into {foc.get('app_id')}:{foc.get('role')} "
                f"(method={act_info.get('method')}"
                f"{'; retried' if retried else ''})."
            )
            overlay.show({"status": "done", "phase": "done"})

    elif stype == "ClickA11y":
        if act_err:
            outcome = "stop"
            reply = f"ClickA11y failed: {act_err}"
            overlay.show({"status": reply, "phase": "failed"})
        else:
            transition = a11y.fingerprint_delta(pre, post)
            if not transition:
                retried = True
                act_info, post = _retry_same(
                    step,
                    announce=announce,
                    pause_ms=pause_ms,
                    raise_only=raise_only,
                    pre=pre,
                )
                act_err = act_info.get("error")
                transition = (not act_err) and a11y.fingerprint_delta(pre, post)
            if act_err:
                outcome = "stop"
                reply = f"ClickA11y failed: {act_err}"
                overlay.show({"status": reply, "phase": "failed"})
            elif transition:
                outcome = "ok"
                tgt = act_info.get("target") or {}
                reply = (
                    f"Clicked {tgt.get('role')} {tgt.get('name')!r} "
                    f"via {act_info.get('method')}"
                    f"{' after retry' if retried else ''} "
                    f"(a11y_delta=True; focus={post.get('summary')})."
                )
                overlay.show({"status": "done", "phase": "done"})
            else:
                outcome = "stop"
                tgt = act_info.get("target") or {}
                reply = (
                    f"ClickA11y soft-fail: no a11y delta after act/retry "
                    f"on {tgt.get('role')} {tgt.get('name')!r} "
                    f"(method={act_info.get('method')}; focus={post.get('summary')})."
                )
                overlay.show({"status": "failed", "phase": "failed"})

    elif stype == "Hotkey":
        if act_err:
            outcome = "stop"
            reply = f"Hotkey failed: {act_err}"
            overlay.show({"status": reply, "phase": "failed"})
        else:
            transition = a11y.fingerprint_delta(pre, post)
            if not transition:
                retried = True
                act_info, post = _retry_same(
                    step,
                    announce=announce,
                    pause_ms=pause_ms,
                    raise_only=raise_only,
                    pre=pre,
                )
                act_err = act_info.get("error")
                transition = (not act_err) and a11y.fingerprint_delta(pre, post)
            keys = "+".join(str(k) for k in (step.get("keys") or []))
            foc = act_info.get("focused_before") or {}
            if act_err:
                outcome = "stop"
                reply = f"Hotkey failed: {act_err}"
                overlay.show({"status": reply, "phase": "failed"})
            elif transition:
                outcome = "ok"
                reply = (
                    f"Hotkey {keys} via {act_info.get('method')}"
                    f"{' after retry' if retried else ''} "
                    f"on {foc.get('app_id')}:{foc.get('title') or foc.get('name')} "
                    f"(a11y_delta=True)."
                )
                overlay.show({"status": "done", "phase": "done"})
            else:
                # Ptyxis/etc often hide tab chrome from AT-SPI — chord delivered,
                # one soft retry done, accept as trusted with changed=false.
                outcome = "ok"
                transition = False
                reply = (
                    f"Hotkey {keys} via {act_info.get('method')}"
                    f"{' after retry' if retried else ''} "
                    f"on {foc.get('app_id')}:{foc.get('title') or foc.get('name')} "
                    f"(a11y_delta=False; chord trusted)."
                )
                overlay.show({"status": "done", "phase": "done"})

    else:
        outcome = "stop"
        reply = f"Unhandled step type: {stype}"
        overlay.show({"status": reply, "phase": "failed"})

    overlay.clear("done" if outcome == "ok" else "failed" if outcome == "stop" else "cancelled")

    return _emit(
        state,
        announce=announce,
        step=step,
        decision=decision,
        outcome=outcome,
        reply=reply,
        observation=post,
        changed=bool(transition) if outcome == "ok" else bool(transition),
        extra={
            "transition": transition,
            "retried": retried,
            "frames_before": act_info.get("frames_before"),
            "frames_after": act_info.get("frames_after"),
            "opened_extra": opened_extra,
            "method": act_info.get("method"),
            "raise_err": act_info.get("raise_err"),
            "raise_only": raise_only,
            "user_confirm": user_confirm,
            "act": {k: v for k, v in act_info.items() if k != "error" or act_err},
        },
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        print(
            "\nFlags:\n"
            "  --raise-only          never launch; require existing frames (Silvio protocol)\n"
            "  --yes / --confirm     auto-confirm policy ask\n"
            "  --no / --abort        auto-abort policy ask\n"
            "  --confirm-timeout N   seconds to wait for y/n (default 60)\n"
            "\nEnv:\n"
            "  BOT_CONFIRM=yes|no    same as --yes / --no\n"
            "  BOT_OVERLAY=0         disable GTK overlay UI\n"
            "  BOT_ALLOW_REBIND=1    allow killall a11y rebind (off by default)\n"
        )
        return 0
    if argv[0] == "--state":
        st = load_state()
        print(
            json.dumps(
                {
                    "action_log": [asdict(e) for e in st.action_log],
                    "last_observation": st.last_observation,
                },
                indent=2,
            )
        )
        return 0

    raise_only = False
    confirm_forced: str | None = None
    confirm_timeout_s = 60.0
    text_parts: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--raise-only":
            raise_only = True
        elif arg in {"--yes", "--confirm"}:
            confirm_forced = "yes"
        elif arg in {"--no", "--abort"}:
            confirm_forced = "no"
        elif arg == "--confirm-timeout":
            i += 1
            if i >= len(argv):
                print("missing value for --confirm-timeout", file=sys.stderr)
                return 2
            confirm_timeout_s = float(argv[i])
        elif arg.startswith("--confirm-timeout="):
            confirm_timeout_s = float(arg.split("=", 1)[1])
        elif arg.startswith("-"):
            print(f"unknown flag: {arg}", file=sys.stderr)
            return 2
        else:
            text_parts.append(arg)
        i += 1

    if not text_parts:
        print("missing user text", file=sys.stderr)
        return 2
    user_text = " ".join(text_parts)
    result = run_turn(
        user_text,
        raise_only=raise_only,
        confirm_forced=confirm_forced,
        confirm_timeout_s=confirm_timeout_s,
    )
    return 0 if result.get("outcome") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
