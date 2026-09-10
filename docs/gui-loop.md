# GUI loop (v1 contract)

This is the first thing to implement. Text in, one desktop gesture, observe, text out. No voice. No omp. Overlay may start as a status string printed to stderr / a log line; the real overlay UI comes next but the **fields** below stay the same.

## Goal of a GUI turn

User asks for something that needs the desktop. The conductor performs **exactly one** OS gesture, shows intent first, checks that the world changed, then replies.

## Inputs

```text
GuiTurnRequest {
  user_text: string          # this turn's utterance only
  action_log: ActionEntry[]  # short history (see below)
  last_observation: Observation | null
}
```

No full screenshot gallery. Optional: attach **one** observation image only if a11y was insufficient last turn (operator flag).

## Outputs

```text
GuiTurnResult {
  announce: string           # one line, human-readable, shown before act
  step: GuiStep              # structured intent
  policy: "auto" | "ask" | "deny"
  outcome: "ok" | "retry" | "stop" | "need_confirm"
  observation: Observation   # after act (or after deny/ask, may be null)
  user_reply: string         # what we tell the user
}
```

## GuiStep (one of)

Prefer accessibility targets. Pixels only when the tree cannot name the control.

```text
FocusWindow   { title_match?: string, app_id?: string }
ClickA11y     { role: string, name: string, window?: string }
TypeText      { text: string, submit?: bool }          # into focused field
Hotkey        { keys: string[] }                      # e.g. ["ctrl","t"]
ClickPoint    { x: number, y: number, button?: "left"|"right" }  # last resort
```

Coordinates are in **logical screen space** shared with the overlay (same scale / monitor mapping as the adapter).

## Observation

```text
Observation {
  source: "a11y" | "screenshot" | "both"
  summary: string            # short; this is what enters model context next
  focused?: { app_id?, title?, role?, name? }
  changed: bool              # did we detect a meaningful delta vs pre-act snapshot?
  evidence_path?: string     # optional local file path; not re-fed as pixels by default
}
```

**Pre-act snapshot:** before `act`, capture a cheap a11y fingerprint (focused node + optional window title). After `act`, compare. If `changed == false` → `outcome: "retry"` once with the **same** `GuiStep`, then `"stop"`.

## Ordering (hard)

```
classify=gui
  → plan one GuiStep
  → policy check
       deny  → user_reply, no act
       ask   → announce + wait confirm → then continue or abort
       auto  → continue
  → announce (status line / overlay fields)
  → pause (default 300–500 ms; abortible)
  → act
  → observe
  → user_reply
```

Never act before announce. Never plan step N+1 because observe failed — only retry same step or stop.

## Action log entry

Appended every turn (success or not):

```text
ActionEntry {
  t: iso8601
  announce: string
  step: GuiStep
  policy_decision: string
  outcome: string
  observation_summary: string
}
```

Trim to last N (design default: 20).

## Minimal success criteria (spike)

When we leave pure design, a spike is “done” if:

1. From a CLI or tiny driver: send `user_text` like “focus the terminal”.
2. Conductor (or a stub planner) emits a `FocusWindow` / `ClickA11y` step.
3. Announce line appears **before** the focus changes.
4. Observation reports an **ACTIVE transition** on the target (`changed: true`): not already focused before the act. “Still Ptyxis because it was already Ptyxis” does **not** count.
5. Target must be **in the AT-SPI tree** before it can become ACTIVE (launch/ensure if missing — e.g. Nautilus/Files).
6. A second turn can use `last_observation` without pasting images into the prompt.

Stub planner is OK for the spike (hardcoded mapping). Real model planning comes after the plumbing works.

## Out of scope here

- Voice / VAD / TTS  
- omp  
- Multi-step plans  
- Set-of-Marks grids as a required path  
- Open Interpreter as the product — optional adapter behind `act` only  

## Depends on

- [turn-cycle.md](turn-cycle.md) — general rules  
- [policy.md](policy.md) — auto/ask/deny  
- [overlay.md](overlay.md) — what announce shows on screen  
- [adapters.md](adapters.md) — AT-SPI / Wayland actuation  
