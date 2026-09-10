# bot

Local desktop conductor for a Bosgame M5: text-first (voice later), Linux Wayland first, one model on llama.cpp, announce-then-act overlay, coding tasks delegated to oh-my-pi (omp).

**Status:** design phase. Architecture and conversation notes live in [`docs/`](docs/).

## Code-task spike

Delegate one scoped repository task to the installed `omp` CLI:

```bash
python3 -m spike --yes "code explain README.md"
python3 -m spike --yes "code add a unit test for the parser"
```

`omp` is the conductor's synchronous **code tool**, not a second brain or an
unsupervised GUI agent. Every `CodeTask`, including reads, waits for explicit
confirmation because omp does not provide path-scoped read isolation. Each turn
invokes at most one
`omp --print --mode json --approval-mode write --cwd <workspace>` process and
returns its outcome in the same JSON envelope as GUI steps. This omp mode allows
the confirmed workspace edits but keeps executable tools behind omp's own gate.
The process runs under `bwrap`: the repository and private `/tmp` are writable,
while the rest of the filesystem is read-only. Project extensions, skills,
rules, LSPs, and executable tools are disabled for this spike.

## Non-goals (v1)

- Not a clone of Codex / Astra voice mode
- No full-duplex voice
- No pet UI
- No Odysseus / OpenHands multi-agent stack

## Hardware

Bosgame M5 — Ryzen AI Max+ 395, Radeon 8060S, 128 GB unified memory.

## License

Apache-2.0 for this repo. Third-party pieces keep their own licenses.

Third-party notices: see [`NOTICE`](NOTICE).
