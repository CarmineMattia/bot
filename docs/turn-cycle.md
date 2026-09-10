# Turn cycle

This is the design unit. Everything else is an adapter.

## Flow

```
1. INPUT        user text (or later: STT transcript)
       │
2. CLASSIFY     talk | code | gui   (one label; ambiguous → ask)
       │
3. PLAN ONE     exactly one next step (or a short reply if talk)
       │
4. POLICY       auto-allow? → else ASK and wait
       │
5. ANNOUNCE     overlay: status line + optional crosshair
       │
6. ACT          gui hand XOR omp XOR speak-only reply
       │
7. OBSERVE      accessibility delta and/or one screenshot check
       │
8. DECIDE       ok → answer user
                fail → retry SAME step once, or stop and say why
                never invent a different step silently
```

## Rules

### One step

A step is something you can announce in one short line:

- “Click *Save* in the dialog”
- “Focus Firefox and open a new tab”
- “Ask omp to add tests in `src/foo.py`”
- “Reply: here’s the short answer…”

Not a step: “set up the project, refactor auth, open the browser, and send the email.”

### Classify

| Label | When | Hand |
| --- | --- | --- |
| `talk` | Question, explanation, no side effect | Reply only |
| `code` | Repo / LSP / edit / test / commit-style work | `omp` tool |
| `gui` | Apps, windows, mouse, keyboard, desktop | GUI adapter |

If both code and GUI are needed, do **one** this turn (usually code first if the blocker is in the repo, GUI first if the blocker is on screen). Say what you deferred.

### Announce-then-act

Before any irreversible or visible OS action:

1. Update overlay status line with the intended action.
2. If the action has screen coordinates or a target widget, show the crosshair / highlight.
3. Brief pause (tunable; design default ~300–500 ms) so a human can abort.
4. Then execute.

Talk-only turns skip the crosshair; they may still use the status line (“thinking…”) if useful.

### Observe

After `act`:

- Prefer accessibility: did the focused window / control / text change as expected?
- Else one verification screenshot (or cropped region), compared to the *intent*, not dumped whole into history.
- Persist: append to **action log** `{step, announce, result, observation summary}`; keep **last observation** only for the next classify.

If observation says nothing changed: **stop or retry the same step**. Do not chain a new invented step.

### Failure

| Outcome | Conductor behavior |
| --- | --- |
| Success | Short user-facing reply; clear overlay highlight |
| Soft fail (timeout, no change) | Retry once same step, then stop |
| Hard fail (denied, crash, policy) | Stop; explain; do not continue the chain |
| User abort during announce pause | Cancel; no act |

## Context budget

Keep in model context:

- System + policy summary
- Recent action log (short)
- Last observation summary
- Current user utterance

Do **not** keep a rolling gallery of full screenshots.

## Voice (later edge)

Same cycle. Mic fills `INPUT`; TTS speaks the final reply and optionally the announce line. Push-to-talk first, then VAD. Fillers (“one moment”) are UX, not a second brain. Full-duplex is out of v1.

Spike: `python3 -m spike --listen 4 --speak` (STT needs Whisper; TTS uses `espeak-ng`). `--listen-file` for offline wav. Not full-duplex.
