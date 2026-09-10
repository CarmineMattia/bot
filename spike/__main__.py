"""Minimal GUI-loop spike for Linux (GNOME/Wayland first).

Implements docs/gui-loop.md success criteria with:
- stub planner (no LLM)
- overlay (GTK UI + stderr log; BOT_OVERLAY=0 disables UI)
- ensure target in AT-SPI tree, then Activate / default.activate
- observe requires an ACTIVE *transition* (Silvio: already-focused ≠ proof)

Run from a normal user session (Ptyxis):

    python3 -m spike "focus files"
    python3 -m spike "focus the terminal"
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from . import a11y, act, overlay, plan, policy

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / ".spike_state.json"


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


def run_turn(user_text: str, pause_ms: int = 400, *, raise_only: bool = False) -> dict[str, Any]:
    state = load_state()
    step = plan.plan_gui_step(user_text)
    if step is None:
        result = {
            "announce": "",
            "step": None,
            "policy": "deny",
            "outcome": "stop",
            "observation": state.last_observation,
            "user_reply": f"Stub planner does not understand: {user_text!r}. Try: focus terminal | focus files | focus editor",
        }
        print(json.dumps(result, indent=2))
        return result

    decision = policy.decide(step)
    announce = plan.announce_for(step)

    if decision == "deny":
        result = {
            "announce": announce,
            "step": step,
            "policy": decision,
            "outcome": "stop",
            "observation": None,
            "user_reply": f"Denied by policy: {announce}",
        }
        print(json.dumps(result, indent=2))
        return result

    if decision == "ask":
        result = {
            "announce": announce,
            "step": step,
            "policy": decision,
            "outcome": "need_confirm",
            "observation": None,
            "user_reply": f"Confirm required before: {announce}",
        }
        print(json.dumps(result, indent=2))
        return result

    pre = a11y.observe()

    # Silvio: if already ACTIVE, do not call that a successful focus change.
    if a11y.already_focused(pre, step):
        result = {
            "announce": announce,
            "step": step,
            "policy": decision,
            "outcome": "already_focused",
            "observation": pre,
            "user_reply": (
                f"Inconclusive: target already ACTIVE before act "
                f"({pre.get('summary')}). Switch to another window first, then retry."
            ),
            "action_log_len": len(state.action_log),
            "raise_only": raise_only,
        }
        overlay.show({"status": result["user_reply"], "phase": "cancelled"})
        overlay.clear("cancelled")
        print(json.dumps(result, indent=2))
        return result

    if raise_only and not a11y.target_in_tree(pre, step.get("app_id") or ""):
        result = {
            "announce": announce,
            "step": step,
            "policy": decision,
            "outcome": "stop",
            "observation": pre,
            "user_reply": (
                f"raise-only: {step.get('app_id')} not in AT-SPI tree. "
                "Open exactly one window manually before the monitor starts."
            ),
            "frames_before": 0,
            "frames_after": 0,
            "opened_extra": False,
            "raise_only": True,
        }
        overlay.show({"status": result["user_reply"], "phase": "failed"})
        overlay.clear("failed")
        print(json.dumps(result, indent=2))
        return result

    overlay.show(
        {
            "status": announce,
            "phase": "announce",
            "pause_ms": pause_ms,
            "target": a11y.target_hint_for_step(step),
        }
    )
    time.sleep(pause_ms / 1000.0)

    overlay.show(
        {
            "status": announce,
            "phase": "acting",
            "target": a11y.target_hint_for_step(step),
        }
    )
    act_info = act.perform(step, raise_only=raise_only)
    act_err = act_info.get("error")
    time.sleep(0.5)
    post = a11y.observe()

    opened_extra = bool(act_info.get("opened_extra"))
    transition = a11y.changed(pre, post, step) and not opened_extra
    outcome: Literal["ok", "retry", "stop", "already_focused"]
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
        overlay.show({"status": f"retry: {announce}", "phase": "announce"})
        time.sleep(pause_ms / 1000.0)
        act_info = act.perform(step, raise_only=raise_only)
        act_err = act_info.get("error")
        time.sleep(0.5)
        post = a11y.observe()
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

    overlay.clear("done" if outcome == "ok" else "failed" if outcome == "stop" else "cancelled")

    entry = ActionEntry(
        t=iso_now(),
        announce=announce,
        step=step,
        policy_decision=decision,
        outcome=outcome,
        observation_summary=str(post.get("summary")),
    )
    state.action_log.append(entry)
    state.last_observation = post
    save_state(state)

    result = {
        "announce": announce,
        "step": step,
        "policy": decision,
        "outcome": outcome,
        "observation": post,
        "user_reply": reply,
        "action_log_len": len(state.action_log),
        "transition": transition if outcome == "ok" else False,
        "frames_before": act_info.get("frames_before"),
        "frames_after": act_info.get("frames_after"),
        "opened_extra": opened_extra,
        "method": act_info.get("method"),
        "raise_err": act_info.get("raise_err"),
        "raise_only": raise_only,
    }
    print(json.dumps(result, indent=2))
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        print("\nFlags:\n  --raise-only   never launch; require existing frames (Silvio protocol)")
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
    if argv[0] == "--raise-only":
        raise_only = True
        argv = argv[1:]
    if not argv:
        print("missing user text after --raise-only", file=sys.stderr)
        return 2
    user_text = " ".join(argv)
    result = run_turn(user_text, raise_only=raise_only)
    return 0 if result.get("outcome") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
