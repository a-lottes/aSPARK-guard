# Spec: activity-trail

| | |
|---|---|
| **Phase** | Specify |
| **Owner** | Product Owner (`/story-time`), Designer (`/look-and-feel`) |
| **Status** | `approved` |
| **Date** | 2026-09-23 (amended; first approved 2026-09-22) |
| **Ticket** | none |

<!-- Handoff: read this block first, the numbered sections below by exception. Whoever
     writes to this spec updates it in the same edit that resolves a clarification or
     changes status: overwrite in place, never append. The block holds one current
     state, never a per-round log; a stale block is a defect, not a cosmetic issue. -->

**Handoff**
- **Status:** `approved` — amended 2026-09-23 after QA B4 (C14) and Q9/A8 (C15, C16); re-approved by the user in the conversation at the spec gate, 2026-09-23. Next step: `/sprint-plan` for the B4 change, with B1 and B2 folded in as fixes.
- **Summary:** aspark-guard keeps a local, metadata-only log of live activity (on by default where `.spark/` exists, capped at 2 MB + 1 rotated file, kept out of git). It records whether each session is busy, idle, waiting or ended, and each subagent's start, finish, duration and short task label, so a read-only cockpit can show what the team is doing right now. Only facts are recorded, never inferred ones. When the harness reports a second finish for one run, "last stop wins": every finish is measured from the run's start, and the latest `agent_run` since the latest start is authoritative (AC-2.2, AC-2.8, C14). Tool-level and phase events are Won't this cycle.
- **Open:** `none` besides the user's own approval tick.
- **Binding ruling:** §4 User Stories for the current stories; §7 Clarifications for what changed since the last round and why
- **On conflict:** the numbered body below wins for everything except `Status`; log the mismatch as a finding at the next `/peer-review` and proceed. Don't stop on it.

<!-- Budget: ~250 lines. -->

## 1. Problem & Goal

- **Problem:** While an aSPARK loop runs, the only record the guard keeps of what the team does is `trail.jsonl`: one line per *finished* subagent. There is no start, so no duration and no "running now". `stop_reason` is `null` in every real line (11 of 11 in `aspark-vscode/.spark/.guard/trail.jsonl`). The main session's state isn't recorded at all. A cockpit that reads only `.spark/` (the loop-dashboard contract) can't answer "is Claude working, done, or waiting for me? Which agent is running on which feature, and for how long?" So the author keeps looking back at the Claude pane, and misses permission prompts and gate questions that sit unanswered.
- **Goal:** Each project that uses aSPARK gets a local file that a reader can use to rebuild the current activity: per session, whether it is busy, idle, waiting for the user or ended, and which subagents are running or have finished (with how long each run took). The file holds metadata only, never content. It stays bounded in size and never slows or blocks Claude.
- **Success signal:**
  1. *Completeness:* during the next full loop in `aspark-vscode` with the guard installed, every subagent run the Claude UI shows has exactly one start line and at least one finish line in the log. The authoritative finish's duration (AC-2.8) is within ±1 s of the run's duration in the session transcript (a one-off manual check by the author; no consumer reads transcripts).
  2. *State fidelity:* in the same loop, every permission prompt the author answered shows up as `waiting` within 2 s of appearing (checked by timestamp against the author's own notes on 5 prompts). No session is left `busy` after Claude finished its turn.
  3. *Privacy:* the NFR-2 marker test finds 0 content leaks. After the loop, `git status` does not list any activity file, while `ledger.jsonl` and `trail.jsonl` show up as before.
  4. *Adoption by the consumer:* the Mission Control spec in `aspark-vscode` names this file as its only live data source, with no fallback to `~/.claude` transcripts.
- **Why now (honest):** Only one consumer needs this, Mission Control, and it is so far a prototype with no spec. If we never build it, the guard loses nothing: gates, ledger and trail work without it. The case for building now is that Mission Control can't be specced honestly without knowing what the producer can actually deliver.
- **Displaces:** Getting the guard through a full loop on someone else's project, which `docs/evidence.md` §6 names as the gap that matters. It also grows a codebase whose README promises "under a thousand lines, readable in one sitting".

## 2. Target Users

- **Primary: the aSPARK author** (Andreas) runs loops in VS Code with Claude Code alongside and the aSPARK Loop Dashboard installed. He wants to glance at the cockpit instead of the Claude pane.
- **Secondary: the cockpit's developer** (the same person, wearing the consumer hat). Needs a stable, versioned, documented line format so the cockpit never has to guess.
- **Also affected, without wanting anything: every guard user.** New hooks run in their sessions too, including in projects without `.spark/`. They must not notice any of this unless they look for the file.
- **Not a target:** anyone wanting a transcript, audit trail or cost/token analytics of Claude's work.

## 3. Assumptions & Open Questions

| # | Assumption / Question | Resolution |
|---|---|---|
| A1 | Original phrasing (user's typed idea): write an additional metadata-only file `.spark/.guard/activity.jsonl` with events `subagent_start`, `agent_run`+`duration_ms`, `tool_use` (all tools), `session_state`, `phase`. The need behind it: a read-only cockpit can rebuild live team activity from `.spark/` alone. File name and event names are kept as the consumer-facing contract. Field-level schema is settled in /sprint-plan within the ACs below. | recorded; `tool_use` and `phase` cut this cycle (C4, C9) |
| A2 | The harness does not deliver a `stop_reason` on SubagentStop in practice (11/11 real lines are `null`), though the guard's own fixture assumes it does. The prototype's `"stop_reason":"end_turn"` is therefore not something we can promise. | assumed from evidence; AC-2.5 forbids inventing it |
| A3 | Claude Code offers hook events for subagent start, prompt submit, turn stop, notification and session end, and a subagent start can be correlated with its finish by `agent_id`. Not verified against the current harness. If one is missing, the story that depends on it drops to what can be observed, and the spec is amended before build. | **accepted as risk by the user** (C13): /sprint-plan spike settles it before any build task |
| A4 | One `agent_id` can run more than once: resumed agents. Real data has `a44343ff…` finishing 5 times. A run is one start followed by its finishes (usually one; see A8), not one agent. | assumed from evidence |
| A5 | `feature` stays an inference, as in the trail (evidence §6). It can be wrong when one session works across two features, and it is `null` for a subagent that starts before its session has written any artifact. | accepted risk |
| A6 | The cockpit reads the file; this spec does not define how it tails, parses, ages or shows it. That belongs to the Mission Control spec in `aspark-vscode`. | recorded |
| A7 | The idea said ".guard/ stays gitignored". The README instead says to commit `ledger.jsonl` and union-merge `.spark/.guard/*.jsonl`. | resolved (C6): only the activity files are ignored; ledger and trail stay committable |
| A8 | The harness can send SubagentStop twice for one continuous run, with no SubagentStart in between (QA B4: first stop at 1.7 s, real end at 12.4 s; seen interactively, not in 13 headless runs). A resume always sends a new SubagentStart (QA AC-2.3, R2). If a resume ever arrives without a start, it is indistinguishable from a double stop and its duration would span both runs. | **accepted as risk by the user** (C16) |
| Q7 | A killed session while others run in parallel. | resolved (C11): facts only; AC-1.7, AC-2.6 |
| Q8 | Idle reminders: `waiting` or `idle`? | resolved (C12): no state change; AC-1.3 |
| Q9 | The constitution says "there is no numeric latency bar"; NFR-1 set p95 ≤ 100 ms and max ≤ 500 ms. | resolved (C15): numbers removed, NFR-1 aligned with the constitution |

## 4. User Stories

**Scope rule for all stories:** "the log" means the activity file of the project whose `.spark/` directory the session works in, found the way the guard already finds its root. Every line in the log carries a UTC timestamp, the event name, the `session_id`, and a format version (AC-4.6). **The log records observed events only.** It never contains an inferred end, abandonment or finish.

### US-1 (Must): See whether each session is busy, idle, waiting or ended

> As the aSPARK author, I want the log to record each Claude session's state as it changes, so that the cockpit can show whether Claude is working, done, or needs me, without my looking at the Claude pane.

**Acceptance criteria:**

- [ ] AC-1.1: Given a session in a project with `.spark/`, when the user submits a prompt, then the log gains one `session_state` line with state `busy` and reason `prompt`.
- [ ] AC-1.2: Given a busy session, when Claude finishes its turn, then the log gains one `session_state` line with state `idle` and reason `stop`. Subagents still running at that moment are not marked finished by this line.
- [ ] AC-1.3: Given a busy session, when Claude asks the user for a permission or an answer, then within 2 s the log gains one `session_state` line with state `waiting`. Its reason comes from a fixed, documented set (e.g. `permission`, `question`) and never contains the notification's message text. Given an idle session, when Claude Code sends a reminder that it is still waiting for a prompt, then no line is written and the state stays `idle`.
- [ ] AC-1.4: Given a `waiting` session, when the next event of that session is recorded (a subagent start or finish, a turn stop, a prompt, the session end), then that event supersedes `waiting`. The guard does not hook ordinary tool calls just to clear `waiting` (C4), and the README states that `waiting` can therefore stay on after the user has answered until the next such event.
- [ ] AC-1.5: Given a session, when it ends (exit, `/clear`, window closed normally), then the log gains one `session_state` line with state `ended`.
- [ ] AC-1.6: Given two sessions working in the same project at the same time, when both change state, then every line names its own `session_id`, and a reader filtering by `session_id` gets each session's states in order, with nothing from the other.
- [ ] AC-1.7: Given a session killed without a clean end (terminal closed, crash), when later sessions start and run in the same project, then the guard writes no `ended`, `abandoned` or other line on the killed session's behalf, and its last recorded line stays its last. Given the README, when a user reads the activity section, then it states that a session without an `ended` line may have been killed, and that judging staleness is up to the reader.

### US-2 (Must): See which subagents are running, and how long each run took

> As the aSPARK author, I want every subagent run recorded when it starts and when it finishes, with its duration, so that the cockpit can show who is working on which feature now and how long the last runs took.

**Acceptance criteria:**

- [ ] AC-2.1: Given a session in a project with `.spark/`, when a subagent starts, then the log gains one `subagent_start` line with `agent_id`, `agent_type` and `feature` (same inference as the trail, `null` if unknown).
- [ ] AC-2.2: Given a recorded `subagent_start`, when that subagent finishes, then the log gains one `agent_run` line with the same `agent_id`, `agent_type` and `feature`, and a `duration_ms` equal to the time between that start and this finish (±50 ms). Given the harness reports that subagent finished again with no new `subagent_start` for its `agent_id` in that session in between (A8), then the log gains one further `agent_run` line per finish, each with `duration_ms` measured from the same start (±50 ms), never `null`. Lines already written are not changed.
- [ ] AC-2.3: Given an `agent_id` that runs a second time (resumed agent, with its own `subagent_start`), when that run finishes, then its `duration_ms` covers only the second run, measured from the latest `subagent_start` of that `agent_id` in that session.
- [ ] AC-2.4: Given a subagent whose start was not recorded (guard installed mid-run, start hook failed, start rotated out), when it finishes, then the `agent_run` line is still written, with `duration_ms: null`, and so is every further finish of that run. No duration is guessed.
- [ ] AC-2.5: Given the harness sends no stop reason, when a run finishes, then `stop_reason` is `null` or absent. The guard never fills in a default such as `end_turn`.
- [ ] AC-2.6: Given a `subagent_start` with no finish, when its session has an `ended` line, then a reader can tell from the log alone that the run is over. When its session has no `ended` line (killed, AC-1.7), then the guard writes no finish for it on its own; the run stays open in the log and the reader judges staleness.
- [ ] AC-2.7: Given this feature is built, when a subagent finishes, then `trail.jsonl` still gains exactly the line it gains today, byte-format unchanged. A double finish (AC-2.2) therefore still adds two trail lines; the trail is not deduplicated (C14).
- [ ] AC-2.8: Given a run with more than one `agent_run` line, when a reader reads the log, then the authoritative finish is the latest `agent_run` with the same `session_id` and `agent_id` after that agent's latest `subagent_start`. Given the README, when a user reads the activity section, then it states this rule, and that a run can briefly show as finished before a later `agent_run` corrects its duration.

### US-3 (Must): The log holds metadata only, and stays on this machine

> As a guard user, I want the activity log to never contain what I or Claude wrote, and never end up in a commit, so that turning it on can't leak prompts, code, secrets or my home path into a repo.

**Acceptance criteria:**

- [ ] AC-3.1: Given hook payloads that carry prompt text, tool input content, tool output, a subagent's last message, or thinking, when any event is recorded, then none of that text appears in the log (verified by NFR-2).
- [ ] AC-3.2: Given any recorded path, when it is written to the log, then it is repo-relative. A path outside the repo root is replaced by a fixed placeholder (e.g. `<outside-repo>`), so no absolute path, home directory or user name appears.
- [ ] AC-3.3: Given a git repo with `.spark/` where the user has added no ignore rules of their own, when a full loop has run, then `git status` lists neither the activity file nor its rotated generation. `ledger.jsonl` and `trail.jsonl` remain visible to git, as before. The guard achieves this from inside `.spark/.guard/` and writes nothing outside `.spark/`.
- [ ] AC-3.4: Given the README, when a user reads the "What it records" section, then it lists every activity event and field, states "metadata only, never content", says the activity files are local and ignored by git while ledger and trail stay committable, and corrects the union-merge advice to cover only the committed logs.

### US-4 (Must): The log is bounded and harmless

> As a guard user, I want the activity log to stay small, never slow or block Claude, and not exist where aSPARK isn't used, so that I have no reason to switch the guard off.

**Acceptance criteria:**

- [ ] AC-4.1: Given a repo without a `.spark/` directory, when every newly hooked event fires, then no file is created, nothing is written to stdout or stderr, and the exit code is 0 (extends the existing negative-case test).
- [ ] AC-4.2: Given any activity hook, when it runs, then it adds nothing to Claude's context. That includes prompt submit, where plain output would reach the model.
- [ ] AC-4.3: Given the current activity file has reached 2 MB, when the next event is recorded, then that file becomes the single rotated generation, replacing any older one, and a new current file is started. No line is split across files, and the two files together never exceed 4 MB plus one line. The ledger and trail are never rotated.
- [ ] AC-4.4: Given an unwritable `.guard/` directory, a corrupt log line, a malformed payload or any exception, when an activity hook runs, then the action proceeds, the exit code is 0, and gate decisions (R1–R4) are the same as without this feature.
- [ ] AC-4.5: Given a project with `.spark/` and no `guard.json` setting for it, when events fire, then the log is written (on by default). Given `guard.json` switches the activity log off, or sets `enabled: false`, then nothing is appended. The switch is documented in the README's configuration block.
- [ ] AC-4.6: Given any line in the log, when a reader parses it, then it carries a format version, and the README documents what that version means. A cockpit can refuse to guess on a version it doesn't know. (Lesson from aSPARK's blocked `template-version-marker`.)
- [ ] AC-4.7: Given `guard.py scan`, when run on a project with a log, then it prints the activity line count and current file size next to the existing ledger and trail counts.
- [ ] AC-4.8: Given a tool call that doesn't launch a subagent (Read, Bash, Grep, MCP tools…), when it runs, then this feature adds no hook invocation to it. The only tool-level trigger this feature may add is on launching a subagent, and only to capture its label (US-5).

### US-5 (Should): See what a running subagent was asked to do, as a short label

> As the aSPARK author, I want a short label of each subagent's task, so that the cockpit shows "PO: challenge the cockpit idea" rather than just "product-owner".

**Acceptance criteria:**

- [ ] AC-5.1: Given the main session launches a subagent with a short description, when the start is recorded, then `subagent_start` carries that description as `task`, cut to at most 80 characters, with newlines and control characters removed.
- [ ] AC-5.2: Given a subagent launched without a short description, when the start is recorded, then `task` is `null`. Nothing from the prompt is used in its place.
- [ ] AC-5.3: Given the full prompt handed to the subagent, when `task` is recorded, then no text from the prompt appears in the log (NFR-2 marker placed in the prompt body).
- [ ] AC-5.4: Given two subagents launched in parallel, when their starts are recorded, then each `task` belongs to its own `agent_id`, never swapped. If the pairing can't be established, `task` is `null`.

### US-6 (Won't, this cycle): See each tool call the team makes

> As the aSPARK author, I want one line per tool call (tool, target, duration, success, agent), so that the cockpit can show a live activity feed.

Cut (C4): it needs a hook on every tool call, which costs about 50 ms per call in every project, including those without `.spark/`. These ACs record the privacy bar for a later cycle and are not built now.

- [ ] AC-6.1: Given any tool call in a project with `.spark/`, when it completes, then the log gains one `tool_use` line with `tool`, `ok`, `ms`, `agent_id`/`agent_type` (`null` for the main session).
- [ ] AC-6.2: Given a non-file tool, when it is recorded, then `target` is never a command, pattern, URL or query. For file tools it is the repo-relative path (AC-3.2).

### US-7 (Won't, until the Mission Control spec asks for it): See the ceremony a session has just started

> As the aSPARK author, I want a line when a session starts an aSPARK ceremony, so that the cockpit shows the phase before the first artifact is written.

Cut (C9): the loop dashboard already derives the phase from the artifacts, and no consumer spec asks for the live signal.

- [ ] AC-7.1: Given a prompt starting with a slash command in the published aSPARK skill list, when submitted, then one `phase` line with the skill name is written; any other prompt writes none, and nothing else of the prompt is recorded.

## 5. Non-Functional Requirements

Bound by the constitution (2026-09-23). Its one active lens, `cli`, binds `scan`/`check` (AC-4.7) and gives hook subcommands a fail-open carve-out; C14 touches neither. NFR-1 follows the constitution's performance rule (C15).

| # | Category | Requirement (measurable) | How it's verified |
|---|---|---|---|
| NFR-1 | Performance | No numeric latency bar (constitution, C15). Every activity hook stays within the 5 s manifest timeout. Ordinary tool calls get no new hook (AC-4.8). Ledger and gate hooks show no measurable regression versus before the feature. The guard's own share per activity hook is measured with `tests/bench_hooks.py` (or a command recorded next to it) and stated in the README's cost section and `docs/evidence.md` with machine and load named, including projects without `.spark/`. | benchmark in `docs/evidence.md` · /peer-review |
| NFR-2 | Security & privacy | A test feeds every hooked event with payloads seeded with unique marker strings in each content field (prompt, tool input content, subagent prompt, tool output, last assistant message, thinking, notification message). **0** markers appear in the log or its rotated generation. No line contains the user's home path. | automated test · /peer-review |
| NFR-3 | Accessibility | N/A: no UI. The file is machine-read, and its presentation belongs to the consumer's spec. | — |
| NFR-4 | Reliability / scale | Two concurrent writers × 500 events each → 0 unparsable lines and 0 lost lines, including across a rotation at 2 MB. A log with a truncated last line keeps getting appended to, and the truncated line is skipped by the existing reader. | automated test · /demo-day |
| NFR-5 | Observability / ops | Failures stay silent by design (fail-open), so AC-4.7's `scan` output is the one place a user can see whether the log is being written. | /demo-day |
| NFR-6 | Compatibility | The existing tests still pass unchanged. Ledger and trail line formats are unchanged. Hook payload fixtures are added for every newly used event, in the shape the harness actually sends (A3), including a double SubagentStop with no start in between (A8). | automated · /peer-review |
| NFR-7 | Auditability | The README invariants still hold: standard library only, no network, `git rev-parse` the only subprocess, and the code "under a thousand lines". If the line promise breaks, the README states the new number rather than keeping a false claim. | /peer-review |

## 6. Out of Scope

- Thinking text, prompts in full, tool inputs/outputs, Bash commands, search patterns, URLs, notification text: never recorded (user's requirement, sharpened by AC-3.1, AC-5.2).
- **Tool-level events (US-6) and any hook on every tool call**, including one just to clear `waiting` sooner (C4).
- **Phase / ceremony events (US-7)** until the Mission Control spec asks for them (C9).
- **Inferring that a session or run has died** (abandoned markers, timeouts, synthetic finishes). Staleness is the reader's call (C11).
- **Suppressing, delaying, rewriting or retracting an `agent_run`** to hide a double finish, or telling a double finish apart from a start-less resume (C14, A8). The reader applies AC-2.8.
- A numeric latency bar for hooks, until the constitution adds one (C15).
- The consumer reading `~/.claude` transcripts. The cockpit itself (Mission Control), and how it shows, tails or ages the log: that is the `aspark-vscode` spec.
- Changing `trail.jsonl`: no duration, start or stop_reason fix there, and no deduplication of double finishes (C14). It stays the committed run counter.
- Folding ledger or trail into the activity log, rotating them, or making them gitignored.
- More than one rotated generation, or time-based retention.
- Token, cost or model metrics; historical analytics.
- Pushing events to the cockpit (socket, network, file watcher on the producer side). The file is the interface.
- Writing `.gitignore`, `.gitattributes` or anything else outside `.spark/`: existing invariant.
- Windows support (existing known limit).

## 7. Clarifications

| # | Date | Question | Resolution |
|---|---|---|---|
| C1 | 2026-09-22 | PO challenge: is every proposed event worth its cost? | Split by cost. Session state and agent runs are Must. Task label is Should. Tool and phase events went to the user (C4, C9). |
| C2 | 2026-09-22 | Orphaned starts, crash between start and stop, resumed agents? | AC-1.5, AC-2.3, AC-2.4, AC-2.6. A run pairs the latest unmatched start per `agent_id`; a missing start gives a `null` duration. Kill handling settled in C11. Pairing refined by C14. |
| C3 | 2026-09-22 | Fabricated `stop_reason`? | Never invented (AC-2.5, A2). |
| C4 | 2026-09-22 | Q1: hooks on every tool call? Options: (a) none; `waiting` clears on the next event; (b) only tools that need permission; (c) all tools. | **(a)**. US-6 → Won't this cycle. AC-1.4 rewritten (stale `waiting` documented), AC-4.8 added, NFR-1 sharpened. |
| C5 | 2026-09-22 | Q2: what may `task` contain? Options: (a) omit; (b) the main session's short label ≤ 80 chars; (c) truncated prompt. | **(b)**, never the prompt. AC-5.1–5.4. |
| C6 | 2026-09-22 | Q3: how does the activity file stay out of git without writing outside `.spark/`? | **(a)**: the guard keeps the activity files ignored from inside `.spark/.guard/`. Ledger and trail stay committable as the README says. This resolves the idea's ".guard/ stays gitignored" (A7). AC-3.3, AC-3.4. |
| C7 | 2026-09-22 | Q4: size cap? | **(b)**: 2 MB + 1 rotated file, ≤ 4 MB total. AC-4.3, NFR-1, NFR-4. |
| C8 | 2026-09-22 | Q5: on or off by default? | **(a)**: on in projects with `.spark/`, switchable off in `guard.json`. AC-4.5. |
| C9 | 2026-09-22 | Q6: phase events? | **(b)**: Won't until the Mission Control spec asks for them. US-7 → Won't. |
| C10 | 2026-09-22 | Clarify pass 2 (after C4–C9): what is still ambiguous enough to change the build? | Two items raised to the user, Q7 and Q8. AC-1.2 sharpened (a turn stop doesn't finish running subagents). AC-5.4 added (parallel launches). A5 extended (`feature` is null before any write). |
| C11 | 2026-09-22 | Q7: killed session while others run in parallel? Options: (a) facts only; (b) mark `abandoned` after T of silence; (c) both. | **(a)**, the user's answer. A clean end is `ended`; nothing is inferred; staleness is Mission Control's call; the README says a session without `ended` may have been killed. AC-1.7 and AC-2.6 finalized; Out of Scope line added. |
| C12 | 2026-09-22 | Q8: idle reminders? Options: (a) no state change; (b) `waiting` with reason `idle`. | **(a)**, the user's answer. Only permission and question notifications set `waiting`. AC-1.3. |
| C13 | 2026-09-22 | A3: hook availability and matching by `agent_id` unverified. | The user accepted it as a risk: a /sprint-plan spike settles it before any build task. |
| C14 | 2026-09-23 | QA B4 (Major, /demo-day): the harness fired SubagentStop twice for one run with no start in between; the log got 1678 ms, then `null`, against a real 12.4 s. Which finish counts? | **"Last stop wins"**, user ruling 2026-09-23. Every finish is measured from the run's latest start, so the second line carries ~12.4 s; the latest `agent_run` since the latest start is authoritative for readers; the cockpit may briefly show "finished" and then be corrected. Trail unchanged, keeps two lines. AC-2.2, -2.3, -2.4, -2.7 amended; AC-2.8, A8, success signal 1, NFR-6 fixture and an Out of Scope line added. Status back to `draft`. |
| C15 | 2026-09-23 | Q9: NFR-1's p95 ≤ 100 ms / max ≤ 500 ms vs the constitution's "no numeric latency bar". | User ruling (matches T12): numbers removed. NFR-1 now requires the 5 s timeout, no hook on ordinary tool calls, no measurable regression versus before the feature, and the guard's own share measured and labelled with the machine. |
| C16 | 2026-09-23 | A8: a start-less resume would look like a double stop. | Accepted as a risk by the user. |

## 8. Design Review

- **Overall impression:**
- **Heuristics findings:**
- **Accessibility notes:**
- **Design risks & required changes:**

---

## ✅ SPEC GATE

*All boxes checked → `/sprint-plan` may start. Any box open → back to `/story-time` or `/look-and-feel`.*

- [x] Problem, goal and success signal are concrete (no buzzwords, no "everyone")
- [x] Every story has testable Given/When/Then acceptance criteria
- [x] Stories are prioritized (MoSCoW) and at least one is a Must
- [x] Non-functional requirements are stated and measurable (or marked N/A with reason)
- [x] Clarify pass done: no ambiguity left unresolved or unparked (C1–C16)
- [x] Open questions are resolved or explicitly accepted as risk (A3 C13, A8 C16, Q9 C15)
- [x] Out-of-scope section is filled (something was consciously cut)
- [x] Constitution (`.spark/constitution.md`) respected, or conflicts recorded as open questions (active since 2026-09-23; `cli` lens checked in §5; NFR-1 aligned, C15)
- [x] Design review done for UI-facing features (or marked N/A with reason): N/A. The producer writes a file and shows nothing to a person. Presentation is owned by the Mission Control spec in `aspark-vscode`, which gets its own design review.
- [x] Line budget respected: Ist ~228 / Soll ~250 (excluding HTML comments)
- [x] Status set to `approved` by the user (first 2026-09-22; re-approved after the B4 amendment 2026-09-23)
