# GUI loop spike

Throwaway-quality driver that exercises [docs/gui-loop.md](../docs/gui-loop.md) on **GNOME Wayland**.

## What it does

1. Stub-plans `FocusWindow` / `TypeText` / `ClickA11y` / `Hotkey` / `CodeTask`
2. Announce via overlay (status bar + crosshair/rect) before act; also logged on stderr
3. Ensure FocusWindow target is in AT-SPI tree (launch/rebind only if **zero** frames)
4. Act: Activate / Overview raise / type / a11y-click / explicit key chord
5. `ok` for FocusWindow only on ACTIVE transition with **stable frame count**
6. `ok` for TypeText if editable focused + ydotool typed; ClickA11y if target found + action/click

## Setup (once per session)

```bash
# a11y
gsettings set org.gnome.desktop.interface toolkit-accessibility true

# input daemon (needs /dev/uinput ACL — already OK for cr1m3 on this machine)
ydotoold -p "$XDG_RUNTIME_DIR/.ydotool_socket" -P 0600 &
export YDOTOOL_SOCKET="$XDG_RUNTIME_DIR/.ydotool_socket"
```

`dnf install ydotool` if missing.

## Run (raise-only — Silvio protocol)

Before Silvio starts monitoring, **baseline must already be**:

- exactly **1** Ptyxis frame  
- exactly **1** Nautilus/Files frame  

Then:

```bash
export YDOTOOL_SOCKET="$XDG_RUNTIME_DIR/.ydotool_socket"
python3 -m spike --raise-only "focus files"
python3 -m spike --raise-only "focus the terminal"
```

`--raise-only` never launches. If frames are 0 → immediate `stop`.

**Pass for Silvio:** ACTIVE Files↔Terminal transitions, frame counts stay at baseline (no growth from monitor start).

Files↔Terminal is the **proof pair** (need a real ACTIVE flip each turn). FocusWindow itself is app-agnostic — same step would raise Firefox or Editor once mapped in the planner.

## Type / Click (after a window is focused)

```bash
export YDOTOOL_SOCKET="$XDG_RUNTIME_DIR/.ydotool_socket"
# focus a terminal first, then:
python3 -m spike "type echo bot-spike-ok"
python3 -m spike "type echo bot-spike-ok and enter"
python3 -m spike "click New Tab"
```


### Ptyxis New Tab via Hotkey

Requires **Ptyxis ACTIVE** first (won’t send Ctrl+Shift+T to gnome-shell/Firefox).

```bash
python3 -m spike --raise-only "focus the terminal"
python3 -m spike "new tab"
# also: "open a new tab" / "please open a new tab"
```

Emits `{"type":"Hotkey","keys":["ctrl","shift","t"],"app_id":"org.gnome.Ptyxis"}`.
Does **not** fall back to `ClickA11y`. `click New Tab` remains the a11y path (fails if no button in tree).

Policy: destructive click names (`Delete`, `Send`, …) → **ask** (overlay `CONFIRM?` + wait).

```bash
# non-interactive confirm / abort
python3 -m spike --yes "click Delete"     # would act after confirm
python3 -m spike --no  "click Delete"     # cancelled, no act
# TTY: type y / n when prompted
python3 -m spike "click Delete"
```

During auto announce pause, typing `q` / `n` on a TTY aborts before act.

`killall` a11y rebind is **off** by default (`BOT_ALLOW_REBIND=1` to opt in).

## Overlay UI

Real GTK surface during announce/acting (status bar + crosshair/rect). On GNOME uses fullscreen click-through fallback (Mutter has no layer-shell).

```bash
# disable UI, keep stderr log only
BOT_OVERLAY=0 python3 -m spike --raise-only "focus files"
```

## Silvio findings absorbed

| Finding | Fix |
| --- | --- |
| Already-focused ≠ proof | `already_focused` outcome |
| Nautilus absent from AT-SPI | ensure/rebind only when zero frames |
| ACTIVE via **new** windows | no `--new-window` on raise path; reject frame-count increase |
| Need real raise | Overview + ydotool (frame count stable in tests) |


## Code task via omp

```bash
# Every code task uses ask policy (confirm with --yes)
python3 -m spike --yes "code explain README.md"
python3 -m spike --yes "omp add parser unit tests"
```

Requires `omp` and `bwrap` on PATH. Workspace must be a git repo root. Runs one sandboxed non-interactive `omp --print` process.
