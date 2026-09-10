# GUI loop spike

Throwaway-quality driver that exercises [docs/gui-loop.md](../docs/gui-loop.md) on **GNOME Wayland**.

## What it does

1. Stub-plans `FocusWindow` (`terminal` / `files` / `editor`)
2. Announce on stderr before act
3. Ensure target is in AT-SPI tree (launch/rebind only if **zero** frames)
4. Try D-Bus Activate + AT-SPI `default.activate`
5. If still not ACTIVE: **raise via GNOME Overview** (`ydotool` Super → type → Enter)
6. `ok` only on ACTIVE transition with **stable frame count**

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

## Silvio findings absorbed

| Finding | Fix |
| --- | --- |
| Already-focused ≠ proof | `already_focused` outcome |
| Nautilus absent from AT-SPI | ensure/rebind only when zero frames |
| ACTIVE via **new** windows | no `--new-window` on raise path; reject frame-count increase |
| Need real raise | Overview + ydotool (frame count stable in tests) |
