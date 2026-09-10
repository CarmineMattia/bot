# Overlay contract

Presence surface for announce-then-act. Dumb on purpose: no chat history, no pet, no agent logic.

## Job

Before a GUI (or risky) act, show:

1. **Status line** — what is about to happen (`announce` string).
2. **Target hint** — crosshair and/or highlight rect when the step has a screen target.

Clear when the turn ends (ok / stop / cancel).

## API (conductor → overlay)

```text
OverlayShow {
  status: string             # required; one short line
  target?: {
    kind: "point" | "rect"
    x: number
    y: number
    w?: number               # rect only
    h?: number
  }
  phase: "announce" | "acting" | "done" | "cancelled" | "failed"
  pause_ms?: number          # announce phase; default from config
}
```

```text
OverlayClear { reason: "done" | "cancelled" | "failed" | "idle" }
```

Conductor may call `OverlayShow` again to update `phase` without changing `target`.

## Behavior

| Phase | Visual |
| --- | --- |
| `announce` | Status + target; pointer still free; abort allowed |
| `acting` | Status may say “doing…”; target can stay |
| `done` | Brief flash optional, then clear |
| `cancelled` / `failed` | Status shows why, then clear |

During `announce`, an abort signal (hotkey or overlay control) must reach the conductor **before** `act`. If abort wins the race, no gesture runs.

Click-through: overlay must not steal normal desktop clicks except an optional abort control.

## Geometry

Same coordinate space as [gui-loop.md](gui-loop.md) `ClickPoint` / a11y bounds from the adapter. Multi-monitor and fractional scaling are the adapter’s problem; overlay trusts the numbers it receives.

## v1 implementation notes (not locked)

- Wayland: layer-shell / always-on-top surface preferred.
- Until UI exists, a **null overlay** that prints `OverlayShow` as one log line still satisfies the GUI-loop spike.
- No screenshots drawn inside the overlay for v1 — status + target only.

## Non-goals

- Chat panel, transcripts, pet, settings UI  
- Streaming token display  
- Replacing the system notification daemon  
