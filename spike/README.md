# GUI loop spike

Throwaway-quality driver that exercises [docs/gui-loop.md](../docs/gui-loop.md) on **GNOME Wayland**.

## What it does

1. Stub-plans `FocusWindow` / `TypeText` / `ClickA11y`
2. Announce via overlay (status bar + crosshair/rect) before act; also logged on stderr
3. Ensure FocusWindow target is in AT-SPI tree (launch/rebind only if **zero** frames)
4. Act: Activate / Overview raise / type / a11y-click
5. `ok` for FocusWindow only on ACTIVE transition with **stable frame count**
6. `ok` for TypeText if editable focused + ydotool typed; ClickA11y if target found + action/click

## Setup (once per session)

```bash
# a11y
gsettings set org.gnome.desktop.interface toolkit-accessibility true

# input daemon (needs /dev/uinput ACL — already OK for cr1m3 on this machine)
ydotoold -p "$XDG_RUNTIME_DIR/.ydotool_socket" -P 0666 &
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

## Type / Click (after a window is focused)

```bash
export YDOTOOL_SOCKET="$XDG_RUNTIME_DIR/.ydotool_socket"
# focus a terminal first, then:
python3 -m spike "type echo bot-spike-ok"
python3 -m spike "type echo bot-spike-ok and enter"
python3 -m spike "click New Tab"
```

Policy: destructive click names (`Delete`, `Send`, …) → `need_confirm` (ask).

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
