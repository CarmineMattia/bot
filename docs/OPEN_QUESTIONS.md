# Open questions

## Q1 — Desktop Linux: GNOME o KDE?

**Impatto:** solo l’adattatore host — come iniettare input su Wayland e come attaccare l’overlay (layer-shell / surface).

**Non cambia:** turn cycle, `gui-loop`, policy, ruolo di omp, scelta modello.

**Stato:** aperto. I contratti restano validi in entrambi i casi.

## Implementation caveats

- Vision: il GGUF vede solo se è caricato anche il **mmproj**.
- Aggressive MTP: serve la build / sidecar documentata dalla quant (es. FastMTP); non reclamare speedup da un `llama-server` vanilla.
- Whisper + Kokoro nominati accanto a un esecutore ≠ loop vocale finché non sono sul bordo dello stesso turn.

## Closed (non riaprire senza motivo)

| Domanda | Decisione |
| --- | --- |
| Ollama vs llama.cpp | llama.cpp |
| Multi-agente vs conduttore | conduttore |
| Visione-first vs a11y-first | a11y-first |
| omp come agente GUI | no — tool codice |
| Full-duplex in v1 | no |
| Pet in v1 | no |
| WSL per mouse / overlay | no |
| Percentuali vs Astra come target | no |
