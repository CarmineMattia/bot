# Policy

Policy is **outside** the model. The conductor checks a rule table before `act`. An uncensored or “aggressive” GGUF is not a reliability feature: it removes refusals, so defaults must be stricter, not looser.

## Modes

| Mode | Meaning |
| --- | --- |
| `ask` | Announce + wait for explicit user confirm |
| `auto` | Announce + short pause, then act |
| `deny` | Refuse; explain |

Default for unknown actions: `ask`.

## Classes

### Auto-allow (navigate / read)

Examples:

- Focus a window, switch workspace/tab
- Scroll, open menus that are reversible
- Read file contents, list directories (non-secret paths)
- Screenshot / accessibility query for observation
- Run read-only commands (`ls`, `git status`, `git diff`, tests that don’t mutate prod)

Still announce; pause can be short.

### Ask always (destructive / external / privileged)

Examples:

- Delete, overwrite, move, or truncate files
- `git push`, force push, rewrite history
- Send messages, email, posts, payments
- Install / uninstall packages; change system settings
- Enter credentials or paste secrets
- Disable firewall / change users / sudo (unless pre-approved allowlist)
- Click “Buy”, “Submit”, “Confirm payment”, “Allow access”
- Anything that leaves the machine (network write) that isn’t on an allowlist

Announce and **block until confirm**. No silent auto-run.

### Deny (v1)

Examples:

- Exfiltrate secrets to remote endpoints not on allowlist
- Disable the policy layer itself without an out-of-band operator action
- Unrestricted shell with `auto` as global default

## Code path (`omp`)

- Treat omp as a **tool**: conductor passes a scoped task + workspace path; waits for outcome.
- Repo writes from omp still respect the same classes (delete / push / secrets → ask).
- Do not give omp a second unsupervised agent loop that can GUI-click around policy.
- Spike policy is `ask` for every `CodeTask`, including reads: current omp
  releases do not enforce a repository boundary for read tools.
- Confirmation gates the whole single delegated task; this spike does not
  intercept or approve individual nested omp tool calls.
- The wrapper uses omp `--approval-mode write`, never `yolo`: confirmed file
  edits can proceed, while executable tools retain omp's own approval gate and
  fail closed in non-interactive mode.
- A `bwrap` mount namespace makes the repository the only persistent writable
  tree (`/tmp` is private); the wrapper fails closed without that containment.
- Project extensions, skills, rules, LSPs, and executable tools are disabled;
  the spike exposes only omp's read/search/edit/write built-ins.

## GUI path

- Prefer targeting by accessibility id/name/role over raw pixel click when available.
- Pixel click only when the tree is missing; then verify with observation.
- Typing shell-sensitive text (`rm`, `sudo`, `passwd`, or `curl`) requires
  confirmation even without Enter because a later gesture can submit it.
- Generic affirmative/dismissive dialog controls (for example “OK”, “Yes”,
  “Accept”, “Continue”, “Sign in”, and “Close”) require confirmation. Known
  reversible navigation targets such as “New Tab” remain automatic.
- `--os`-style executors that auto-run code without confirm **must** sit behind this policy gate. Never point an uncensored model at auto_run and call that “done.”

## Operator controls

Minimum knobs (design):

- Global: `strict` (everything ask except pure talk) vs `normal` (table above)
- Per-session allowlist (paths, hosts, apps)
- Abort key / overlay cancel during announce pause
- Kill switch: stop conductor, freeze GUI hand

Spike (`spike/confirm.py`): policy `ask` shows overlay `CONFIRM? … [y/n]`, then waits for TTY `y`/`n`, or `--yes`/`--no` / `BOT_CONFIRM`. Auto announce pause is abortible on a TTY (`q`/`n`).

## Logging

Log every policy decision: `{action, class, decision, user_confirm?}`. Logs stay local. Do not ship them unless the operator opts in later.
