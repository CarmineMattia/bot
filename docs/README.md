# Design docs

Design-first. Code starts only against these contracts.

| Doc | What it locks |
| --- | --- |
| [overview.md](overview.md) | Product shape, one brain, three exits |
| [turn-cycle.md](turn-cycle.md) | classify → one step → announce → act → observe |
| [gui-loop.md](gui-loop.md) | **First build target** — GUI turn I/O, no voice |
| [overlay.md](overlay.md) | Crosshair + status line API |
| [policy.md](policy.md) | auto / ask / deny |
| [adapters.md](adapters.md) | Linux Wayland first; Win later |
| [notes.md](notes.md) | What we discarded and why |
| [CONVERSATION.md](CONVERSATION.md) | Recap del filo di design (memoria) |
| [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) | GNOME locked; caveat mmproj/MTP |

## Build order

1. ~~Contracts for turn + GUI loop + overlay~~ (this folder)
2. **Spike in progress:** `spike/` — announce → Activate → AT-SPI observe (GNOME). Observe confirmation still weak under agent/session ACL; visual check via Silvio OK.
3. Real overlay UI on Wayland
4. Policy gate wired for ask/deny
5. omp tool wrapper
6. Voice edge (same turn)
