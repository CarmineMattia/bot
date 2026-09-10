# Adapters

The turn cycle does not change per OS. Only the **GUI hand** and **perception** adapters change.

## Priority

1. **Linux Wayland** (primary) — Bosgame M5 day-to-day
2. **Windows** native (later)
3. **WSL** — brain (llama.cpp) only if needed; **never** for mouse/overlay/GUI. Native Linux (GNOME Wayland) owns the desktop adapter.

## Perception

| Platform | Primary | Fallback |
| --- | --- | --- |
| Linux | AT-SPI (a11y tree: role, name, bounds) | Screenshot + vision (mmproj) |
| Windows | UI Automation | Screenshot + vision |

Vision verifies and covers apps that expose a poor tree. Do not make “guess pixel coordinates only” the default path.

## Actuation (GUI hand)

Design requirement, not a locked vendor:

- Focus window, move pointer, click, type, key combos
- Wayland: prefer portals / compositor-friendly tools (`ydotool`, `wtype`, etc. as researched at implement time) over X11-only assumptions
- Optional reuse of Open Interpreter `--os` **behind** the conductor + policy — it is an executor, not the product brain

Coordinate space: announce overlay and click targets must share the same display transform (scale factor, multi-monitor).

## Presence (overlay)

Platform-agnostic contract:

- Always-on-top, click-through except cancel hit-target if any
- Status line: one short string of the pending/current step
- Crosshair / highlight: optional rect or point for the next click
- Show *before* act; clear on success/cancel/fail

Implementation can be GTK/Qt/layer-shell on Wayland; details deferred until the contract above is coded against.

## Code hand

Same on all platforms: invoke `omp` with workspace + task; parse result; return to conductor. No GUI required.

## Brain

`llama.cpp` server (OpenAI-compatible HTTP). Model + optional mmproj configured by the operator. Conductor talks to one base URL.

## What adapters must not do

- Own the turn loop
- Bypass policy
- Accumulate screenshot history into the model context
- Start a second unsupervised agent
