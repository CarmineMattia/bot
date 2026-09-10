# Open questions

## Q1 — Desktop Linux: GNOME o KDE?

**Decisione:** **GNOME** (Wayland) sul Bosgame M5 — `XDG_CURRENT_DESKTOP=GNOME`.

**Impatto adapter:** overlay via layer-shell / GTK; focus via `org.freedesktop.Application.Activate` (+ AT-SPI `default.activate`). GNOME Shell `FocusApp` / `Introspect.GetWindows` are often `AccessDenied` from normal clients — do not depend on them.

**Stato:** chiuso.

## Implementation caveats

- Vision: il GGUF vede solo se è caricato anche il **mmproj**.
- Aggressive MTP: serve la build / sidecar documentata dalla quant (es. FastMTP); non reclamare speedup da un `llama-server` vanilla.
- Whisper + Kokoro nominati accanto a un esecutore ≠ loop vocale finché non sono sul bordo dello stesso turn.
- **GNOME Wayland focus-steal:** raise existing windows via Overview + `ydotool` (Super → query → Enter). Do not use `--new-window` for FocusWindow. Requires `ydotoold`.
- **Ptyxis a11y:** often exposes only frame→panel; TypeText uses ACTIVE typeable-app fallback when no FOCUSED editable node exists.
- **killall rebind:** off by default; `BOT_ALLOW_REBIND=1` required (was too destructive on auto FocusWindow).

## Closed (non riaprire senza motivo)

| Domanda | Decisione |
| --- | --- |
| GNOME vs KDE | GNOME Wayland |
| Ollama vs llama.cpp | llama.cpp |
| Multi-agente vs conduttore | conduttore |
| Visione-first vs a11y-first | a11y-first |
| omp come agente GUI | no — tool codice |
| Full-duplex in v1 | no |
| Pet in v1 | no |
| WSL per mouse / overlay | no |
| Percentuali vs Astra come target | no |
