# Overview

## Product

**bot** is a local desktop conductor: you speak or type, it routes one step of work, shows you what it will do, does it, checks the result, then answers.

It is not a Codex/Astra clone, not a pet, and not a multi-agent stack.

Target machine: Bosgame M5 (Ryzen AI Max+ 395, Radeon 8060S, 128 GB unified). Primary desktop: Linux Wayland. Text works without voice; voice is a later edge on the same turn.

## One brain, three exits

```
                 ┌──────────────┐
  text / voice → │  conductor   │ → reply (text, later TTS)
                 │  (one model) │
                 └──────┬───────┘
                        │ classify once
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
      talk-only      code (omp)    GUI (OS)
          │             │             │
          │             │        announce → act → observe
          │             │             │
          └─────────────┴─────────────┘
                        │
                   overlay (presence)
```

| Exit | Role | v1 |
| --- | --- | --- |
| **Presence** | Overlay: crosshair + one status line *before* the gesture | Required |
| **GUI hand** | Click, type, focus windows | Required (Linux first) |
| **Code hand** | oh-my-pi (`omp`) on a repo task | Required as a tool, not a second agent |
| **Voice** | Same turn with mic optional | Deferred; system must work with text only |

One model on **llama.cpp** (Qwen3.8-27B GGUF in this environment). Vision when mmproj is loaded; without it the conductor is text-only and must lean on accessibility trees.

## Design invariants

1. **The turn cycle is the product.** Adapters (Interpreter, custom scripts, AT-SPI, Win UIA) are replaceable.
2. **One step per turn** until observe succeeds. No hidden 20-step plans.
3. **Announce before act.** The user sees the next gesture first.
4. **Dual perception.** Prefer OS accessibility (AT-SPI on Linux); vision verifies and fills gaps. Do not pile screenshots into context — keep an action log + last observation.
5. **Policy lives outside the model.** See [policy.md](policy.md).

## Explicit non-goals (v1)

- Full-duplex voice / GPT-Live style
- Pet UI or character
- Odysseus, OpenHands, Docker harness as the core
- Second vision-only model
- Matching Astra “judgment” — local copies the shape, not the training
