# Design notes (from the exploration chat)

Compressed decisions. Full chat was exploratory and contradictory; this file keeps what we kept.

## What we kept

- **Local conductor**, not “Astra clone”
- **One model** on llama.cpp (operator’s Qwen3.8-27B GGUF)
- **Announce-then-act** overlay as the product surface
- **omp** for coding (already in use); GUI for desktop control
- **Text-first**; voice later on the same turn
- **Linux Wayland first**
- **Apache-2.0** for this repo; respect third-party licenses
- Commercial packaging of a machine/service is possible later with notices — do not brand as Astra / Open Interpreter / official Alibaba weights

## What we discarded for v1

| Idea | Why discarded |
| --- | --- |
| Pet UI | Skin, not core |
| Full-duplex voice | Hard; not required for a useful conductor |
| Odysseus as core | Extra latency and scope |
| OpenHands / Docker harness as core | Heavy; coding vs GUI confused |
| “Scartare omp perché cieco alla GUI” | Wrong category — keep omp as code tool |
| Percentages vs Astra (55–85%) | Invented; do not use as targets |
| Uncensored as reliability upgrade | Removes refusals; needs *stricter* policy |
| `--vision` as magic Set-of-Marks flag | Not a substitute for a real announce/observe loop |
| Ollama-required stack | Operator already on llama.cpp |

## Honest gaps the chat exposed

1. GGUF vision needs **mmproj** (and MTP “aggressive” needs whatever extra files/build that quant actually requires — verify before claiming speedups).
2. Whisper/Kokoro named beside Interpreter ≠ a voice loop.
3. Terminal logs ≠ “see what it does”; overlay is the missing product piece.
4. Open Interpreter is an **executor** (Apache-2.0), model-agnostic — not Codex and not Astra.

## Build order (when leaving design)

1. Contracts: [gui-loop.md](gui-loop.md) + [overlay.md](overlay.md) (done)
2. Spike: null overlay + one GUI step + a11y observe
3. Real overlay UI
4. Policy gate
5. omp wrapper
6. Voice edge
