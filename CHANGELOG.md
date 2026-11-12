# Changelog

What changes for you from one version to the next. The details of each item are in
the [README](README.md); what has and has not been exercised is in
[`docs/evidence.md`](docs/evidence.md).

## 0.3.0 — 2026-11-12

### Added
- **Code waits for an approved plan.** A new rule, `code-requires-approved-plan`, denies
  a `Write` or `Edit` to a file outside `.spark/` while the session has written a spec
  or plan and none of those features has an approved plan yet. Sessions that never
  touch a trail are not held.
- **`"plan_first_scope": "always"`** for projects where all work goes through aSPARK:
  every code write is denied unless some feature has an approved, unreleased plan. This
  also catches code written before any spec exists.
- **`"plan_first_exempt"`**: path patterns the rule never holds.

### Changed
- **The gate hook now also looks at writes outside `.spark/`.** It ran on every
  `Write`/`Edit` before and returned at once for these files; now it reads the ledger
  and, at most, a few plan headers. Nothing changes in projects without `.spark/`.
- The rule is on (`block`) by default. Set it to `"warn"` or `"off"` under `"rules"` in
  `.spark/guard.json` if it does not fit your project.

### Known limits
- Not replayed over real project history before release, unlike the first three rules.
  See `docs/evidence.md` §10.
- Writes through `Bash` are not seen (issue #2), as for every rule.

## 0.2.0 — 2026-09-23

### Added
- **A live activity log for aSPARK projects.** `.spark/.guard/activity.jsonl` now shows,
  for every Claude session, whether it is working, done with its turn, waiting for you
  at a permission prompt, or closed. A dashboard that reads only your project can show
  what the team is doing right now, without you looking back at the Claude pane.
- **Subagent runs you can follow.** Every subagent's start and finish is logged, with
  how long the run took, which feature it most likely belongs to, and a short label of
  what it was asked to do (file paths masked).
- **`guard.py scan` reports the activity log**: whether it is on, how many lines it
  holds and how large it is.
- **An `"activity"` switch in `.spark/guard.json`** to turn the log off. It is on by
  default.

### Changed
- **The guard runs at a few more moments**: when you send a prompt, when Claude
  finishes a turn, on a permission prompt, when a session ends, and when a subagent is
  launched or starts. Each adds a Python start-up, never blocks anything, and does
  nothing in projects without `.spark/`. The measured cost is in `docs/evidence.md` §9.
- **The new log stays on your machine and stays small.** It is kept out of git
  automatically. It holds only ids, times and values from a fixed list, never prompts,
  tool output or messages. It is capped at 2 MB plus one older file.

### Fixed
- Nothing. This release adds; the ledger, the trail and every gate rule behave as in
  0.1.0.

## 0.1.0

First complete version: gate enforcement, the hash ledger, content-bound overrides,
the template contract and the agent-run trail.
