# Plan: activity-trail

| | |
|---|---|
| **Phase** | Plan |
| **Owner** | Engineering Manager (`/sprint-plan`) |
| **Input** | `.spark/activity-trail/spec.md` (must be `approved`) |
| **Status** | `approved` |
| **Date** | 2026-09-22 |

<!-- Handoff: read this block first, the numbered sections below by exception. Whoever
     writes to this plan updates it in the same edit that changes a task's status or
     the plan's own status: overwrite in place, never append. The block holds one
     current state, never a per-round log; a stale block is a defect, not a cosmetic
     issue. -->

**Handoff**
- **Status:** `approved` — approved by the user at the plan gate, 2026-09-22. Next ceremony step: `/increment`, starting with T1 (hook spike; part of it needs the user in a live interactive session).
- **Summary:** New module `activity.py` appends v1 metadata-only lines to `.spark/.guard/activity.jsonl` from one subcommand per new hook. A run's duration is paired when the line is written, by scanning the log itself. Every append and the single 2 MB rotation run under an `fcntl.flock`. A self-ignoring `.spark/.guard/.gitignore` keeps `activity*` out of git. **T1 (hook spike) gates every build task.**
- **Open:** `1 task not done` (T1–T11 done; T12 open). T1 findings changed D2 by user ruling — see Deviations D-T1-1…5.
- **Binding ruling:** §3 Task Breakdown for current task status; a plan revision after review/QA findings updates §1/§3 in place, never a new section
- **On conflict:** the numbered body below wins for everything except `Status`; log the mismatch as a finding at the next `/peer-review` and proceed — don't stop on it.

<!-- Budget: ~300 lines. -->

## 1. Architecture Decision

- **Context:** The guard is a single-entry Python stdlib plugin (`bin/guard.py` → `cli.main`, one subcommand per hook). It must be fail-open and silent without `.spark/`, and it already appends JSONL with `ledger.append_to`. Today it hooks PreToolUse/PostToolUse (Write/Edit), SubagentStop and SessionStart. The spec adds session state and subagent runs. These need five hook events (UserPromptSubmit, Stop, Notification, SubagentStart, SessionEnd) that the guard has never used and that are unverified against the installed harness (A3). It also needs a start→finish pairing with ±50 ms precision, a 2 MB rotation that holds up under concurrent writers, and an ignore rule written from inside `.spark/.guard/`. Two facts inherited from the codebase: `src/` is already **1,533 physical lines**, so the README's "under a thousand" claim is already false (NFR-7). And `ledger.utc_now()` has 1 s resolution.
- **Decision:** Add one module, `src/aspark_guard/activity.py`, with one `cli.py` handler per new event, in the house style. The file is append-only, and only facts go into it. Details:
  - **D1 Line format v1.** Every line has `v` (1), `ts` (UTC ISO with ms, `2026-09-22T10:00:00.123Z`), `event` and `session_id`. The per-event fields are:
    - `session_state`: `state`, `reason`.
    - `subagent_start`: `agent_id`, `agent_type`, `feature`, `task`.
    - `agent_run`: `agent_id`, `agent_type`, `feature`, `duration_ms`.

    `stop_reason` is **absent** (AC-2.5). No field holds a path, so AC-3.2 holds because nothing path-shaped is recorded, and the NFR-2 test proves it. Keys are sorted, the same as ledger and trail. `ledger.utc_now` stays untouched, so the ledger and trail byte format does not change.
  - **D2 Reasons are drawn from fixed allowlists, never copied from the payload.**
    - UserPromptSubmit → `busy/prompt`.
    - Stop → `idle/stop`.
    - Notification → `waiting/permission` or `waiting/question`, keyed only on the payload's type field. `message` is never read. The hooks.json matcher is limited to those types, so idle reminders never start the guard at all (AC-1.3, C12).
    - SessionEnd → `ended/` plus one of {`clear`, `logout`, `exit`, `other`}.
  - **D3 Pairing happens when the finish line is written.** On SubagentStop the guard reads `activity.jsonl.1` (if present) and then `activity.jsonl`, in that order. Raw lines are pre-filtered by an `agent_id` substring check before any JSON parsing, so a 4 MB scan stays cheap. It takes the latest `subagent_start` of that session and `agent_id` that has no `agent_run` after it. The duration is now − start in ms. With no match, `duration_ms: null` (AC-2.3, AC-2.4). There is no second source of truth.
  - **D4 One locked write path, activity only.**
    - The guard takes `fcntl.flock` on `.spark/.guard/activity.lock`, using non-blocking retries with a 500 ms deadline. If the deadline passes it drops the line silently (fail-open).
    - It then appends a newline if the file's last byte isn't `\n` (NFR-4, truncated tail).
    - If the size is ≥ 2 MB, it does `os.replace(activity.jsonl, activity.jsonl.1)`.
    - Then it appends one line.

    Ledger and trail keep using `ledger.append_to`, unchanged and never rotated.
  - **D5 Git.** On the first activity write, the guard creates `.spark/.guard/.gitignore` if it is absent, containing `/.gitignore` and `/activity*`. The file ignores itself, so `git status` stays clean. It never overwrites an existing file, and ledger and trail stay visible (AC-3.3).
  - **D6 Label (Should).** A second PreToolUse matcher entry for the subagent tool (name settled by T1) calls the **same** `pre-tool-use` command. That keeps the gate entry at index 0 and keeps `test_install.hook_commands()` valid. The handler branches on `tool_name` before any gate logic. It stores `{ts, session_id, agent_type, task}` in `activity.pending.jsonl`. `task` is the payload's short description, with control characters removed and whitespace collapsed, cut to ≤ 80 chars, otherwise `null`. SubagentStart takes the task **only if exactly one** pending entry for that session and type is younger than 60 s. Every matching entry is used up either way, and an ambiguous match gives `null` (AC-5.4). If T1 shows that SubagentStart carries the description or a `tool_use_id` link, the guard uses that instead and the pending file goes away.
  - **D7 Config.** `"activity": true` goes into `config.DEFAULTS`, and the `enabled: false` gate applies to it like every other key (AC-4.5).
  - **D8 Reader contract (README).**
    - A session's state is its latest `session_state`.
    - Any later line of that session supersedes `waiting` and means busy.
    - A missing `ended` line means the session may have been killed.
    - A run with no `agent_run` in an `ended` session is over.
    - `v` goes up on any change to event names, fields or their meaning. Readers refuse a `v` they don't know.
- **Alternatives considered:**
  | Alternative | Why rejected |
  |---|---|
  | Extend `trail.jsonl` with starts and durations | Spec §6 forbids it. The trail is the committed run counter, and AC-2.7 requires its bytes unchanged |
  | A state snapshot file (`activity.json` rewritten on every event), or a side index of open starts | Rewriting on every event races between concurrent sessions. A snapshot or index is a second source of truth that can drift from the log. Scanning ≤ 4 MB with a substring pre-filter fits NFR-1 (proven in T12) |
  | Write raw start/stop only and let the consumer compute `duration_ms` | AC-2.2 puts `duration_ms` in the log. Every consumer would have to re-implement pairing, resume handling and rotation stitching |
  | Rotate with `os.replace` and no lock | Two writers that both see ≥ 2 MB rotate twice. The second rename replaces the first generation, so up to 2 MB is lost. That fails NFR-4 |
  | SQLite (stdlib) | Can't be tailed as text, and breaks the "the file is the interface" contract (A1, §6). Readers would need a driver |
  | Ignore via root `.gitignore` or `.git/info/exclude` | Writes outside `.spark/`, which breaks an existing invariant (§6, AC-3.3) |
  | A committable (non-self-ignoring) `.spark/.guard/.gitignore` | It shows up as `??` in every adopting repo and asks the user to decide something. The guard recreates it anyway, so committing it buys nothing |
  | Task label from `PostToolUse` of the subagent tool, or from `transcript_path` | PostToolUse fires only when the run is over. Reading transcripts is reading content (US-3, §6) |
  | One generic `activity` subcommand that dispatches on `hook_event_name` | Works, but breaks the codebase's one-subcommand-per-event pattern for no gain |
- **Consequences:**
  - *Easier:* the cockpit gets one versioned, tailable file with durations already computed. The log alone is enough for pairing, so there is nothing to keep consistent.
  - *Harder:* five new hook invocations per turn or subagent, about 50 ms each, paid in every project, including those without `.spark/` (documented in T11/T12). `fcntl` makes the POSIX-only limit structural. `src/` grows by an estimated ~260 lines to about 1,800, and the README has to state that number (NFR-7). A `.gitignore` file appears under `.spark/.guard/`.
- **User rulings (2026-09-22):**
  - **Q1 → (a).** NFR-6 says existing tests pass "unchanged", but adding hooks means extending `EXPECTED_EVENTS` in `tests/test_install.py`. The user ruled that this is allowed, as the only edit to an existing assertion. It is logged at `/peer-review` as keeping the test's intent: every event the plugin relies on is wired.
  - **Q2 → (a).** The README's line-count claim is replaced by the number `wc -l` measures, recorded in the README (T11) and in `docs/evidence.md` (T12), as NFR-7 allows.
  - **Q3.** No hooks reference was supplied. T1 records the facts, and my field-name expectations stay hypotheses until then.

## 2. Affected Components

Scoped by hand: no blast-radius tool was passed and aspark-graph is unavailable. I read every file below.

- **New:** `src/aspark_guard/activity.py` (write path, lock, rotation, gitignore, pairing, labels, allowlists). Tests: `tests/test_activity.py`, `tests/test_activity_rotation.py`, `tests/test_activity_privacy.py`. Benchmark: `tests/bench_hooks.py` (not collected by `discover`). Payload fixtures under `tests/fixtures/payloads/`.
- **Changed:**
  - `src/aspark_guard/cli.py`: 5 handlers, a subagent-tool branch in `handle_pre_tool_use`, an activity call in `handle_subagent_stop`, and `scan`.
  - `src/aspark_guard/config.py`: `activity` key.
  - `src/aspark_guard/trail.py`: `_feature_for_session` becomes public `feature_for_session`. Behaviour and output are identical.
  - `hooks/hooks.json`: 5 events plus 1 PreToolUse matcher.
  - `bin/guard.py`: usage docstring.
  - Tests: `tests/test_install.py` (`EXPECTED_EVENTS` extended, per ruling Q1), `tests/test_negative_case.py`, `tests/test_failopen.py` (extended, not altered).
  - Docs: `README.md`, `docs/evidence.md`, `.gitattributes` (union merge limited to ledger and trail).
- **No new dependencies.** `fcntl`, `os.replace` and `unicodedata` are stdlib. No new subprocess.
- **Consumer:** `aspark-vscode` is read-only context. The format contract it gets is D1 plus D8 (README).

## 3. Task Breakdown

| # | Task | Story | Covers (AC / NFR) | Depends on | Status | Definition of Done |
|---|---|---|---|---|---|---|
| T1 | **A3 hook spike** (no build code). A throwaway probe plugin, loaded via `--plugin-dir` from the scratchpad, appends each payload's key names, enum values and a monotonic ms stamp to a scratch file outside any repo, then gets deleted. Run it once headless (`claude -p`) and once in an **interactive session by the author** (permission prompt, AskUserQuestion, ≥ 60 s idle reminder, `/clear`, exit) | US-1, US-2, US-5 | A3, NFR-6, AC-1.3, AC-2.1, AC-2.2, AC-5.1 | – | `done` | `docs/evidence.md` gains §7 "Hook spike". It records: `claude --version`; the probe command; for each of UserPromptSubmit, Stop, Notification, PermissionRequest (fallback candidate), SubagentStart, SubagentStop, SessionEnd and PreToolUse on the subagent tool, whether it fired as a **plugin** hook and its key list; the subagent tool's name and whether its `tool_input` has a short description; the Notification type values for the permission prompt, the AskUserQuestion and the idle reminder; the hook-vs-screen latency for 5 permission prompts; the SessionEnd reasons for `/clear` and exit; whether SubagentStart and SubagentStop `agent_id` match across 2 parallel same-type runs and 1 resumed run. Each row of the T1-outcome table below ends in Go or Degrade. Redacted fixtures exist for every event that was observed, with no real content and no home path. No file under `src/` or `hooks/` changed — files: docs/evidence.md, tests/fixtures/payloads/user_prompt_submit.json, tests/fixtures/payloads/stop.json, tests/fixtures/payloads/notification_permission.json, tests/fixtures/payloads/notification_idle.json, tests/fixtures/payloads/subagent_start.json, tests/fixtures/payloads/session_end.json, tests/fixtures/payloads/pre_tool_use_task.json |
| T2 | **Walking skeleton:** `activity.record()` (unlocked append for now), `activity` config key, `user-prompt-submit` and `stop` handlers, both wired in `hooks.json`, `EXPECTED_EVENTS` extended (ruling Q1) | US-1 | AC-1.1, AC-1.2, AC-4.2, AC-4.5, AC-4.6 | T1 | `done` | Feeding the T1 fixtures through `cli.main` writes exactly one `busy/prompt` line and one `idle/stop` line, each with `v:1`, a ms `ts`, `event` and `session_id`. Stdout is empty for both. `{"activity": false}` writes nothing. `test_install` runs both new manifest commands through a shell from a path containing a space, with exit 0 and empty stderr. The full suite is green — files: src/aspark_guard/activity.py, src/aspark_guard/cli.py, src/aspark_guard/config.py, hooks/hooks.json, bin/guard.py, tests/test_activity.py, tests/test_install.py |
| T3 | Silence and fail-open for every new subcommand | US-4 | AC-4.1, AC-4.2, AC-4.4, AC-4.5 | T2 | `done` | `test_negative_case` covers every new subcommand: no `.spark/` → exit 0, empty stdout, tree unchanged. `test_failopen` feeds each new subcommand garbage, a non-dict and an empty payload, plus an unwritable `.guard/` → exit 0, no output. `enabled:false` → nothing appended. A PreToolUse Write against a draft spec still denies with the new code present — files: tests/test_negative_case.py, tests/test_failopen.py, tests/test_activity.py |
| T4 | Locked write path: flock, truncated-tail repair, 2 MB rotation to `activity.jsonl.1`, `.gitignore` created if absent | US-4, US-3 | AC-4.3, AC-3.3, NFR-4 | T2 | `done` | Tests prove each of these. The file is pre-filled to 2 MB − 50 KB, then 2 subprocess writers × 500 events run → rotated + current together hold prefill + 1000 lines, 0 unparsable. After a second rotation only one generation exists, and the total is ≤ 4 MB + 1 line. An append after a truncated last line parses, and `read_jsonl` skips the truncated line. In a `git init` temp repo, `git status --porcelain` lists no `activity*` and no `.gitignore`, while ledger and trail stay visible (skipped if git is missing). An existing `.gitignore` is not modified. Ledger and trail are never rotated — files: src/aspark_guard/activity.py, tests/test_activity_rotation.py |
| T5 | `notification` and `session-end` handlers, allowlisted reasons, matcher restricted to permission and question types | US-1 | AC-1.3, AC-1.4, AC-1.5, AC-1.6, AC-1.7 | T4 | `done` | Tests show: a permission fixture gives `waiting/permission` and a question fixture gives `waiting/question` (if T1 found one); an idle-reminder fixture gives no line; the notification `message` never appears; an unknown type gives no line. SessionEnd gives `ended/<allowlisted reason>`, and an unknown reason maps to `other`. Two interleaved `session_id`s filter cleanly, each in order. No event writes a line for another session, and nothing is ever written as `abandoned`. `test_install` asserts that the Notification matcher excludes the idle type — files: src/aspark_guard/activity.py, src/aspark_guard/cli.py, hooks/hooks.json, bin/guard.py, tests/test_activity.py, tests/test_install.py |
| T6 | `subagent-start` handler: `subagent_start` line with `agent_id`, `agent_type`, `feature` | US-2 | AC-2.1, AC-2.6 | T4 | `done` | Given a ledger write by the session → `feature` is inferred, the same value the trail gets. With no write → `feature` is `null`. Stdout is empty. A start with no stop, followed by `ended`, leaves no synthetic `agent_run` in the log. `trail.feature_for_session` is renamed and `test_trail` passes untouched — files: src/aspark_guard/activity.py, src/aspark_guard/cli.py, src/aspark_guard/trail.py, hooks/hooks.json, bin/guard.py, tests/test_activity.py, tests/test_install.py |
| T7 | `agent_run` on SubagentStop, with the duration paired across rotated + current files | US-2 | AC-2.2, AC-2.3, AC-2.4, AC-2.5, AC-2.7 | T6 | `done` | Tests show: `duration_ms` is within ±50 ms of a controlled gap; a resumed `agent_id` measures only its second run; a start in `.1` with the stop in the current file still pairs; a missing start gives `null`; no `stop_reason` key appears even when the payload has one. A golden test asserts the trail line has the same key set and `json.dumps` form as before the feature, byte for byte except `ts`. The trail is still written with `activity:false`, and activity is still written with `trail:false` — files: src/aspark_guard/activity.py, src/aspark_guard/cli.py, tests/test_activity.py, tests/test_trail.py |
| T8 | Task label (per T1's pairing variant): PreToolUse subagent-tool matcher, same `pre-tool-use` command, sanitised `task`, exactly-one pairing | US-5 | AC-5.1, AC-5.2, AC-5.3, AC-5.4, AC-4.8 | T6 | `done` | Tests show: an 80+ char description with `\n` and `\x1b` becomes ≤ 80 chars with no control characters; no description gives `task: null`; two pending entries of the same type give `null` for both starts; different types each get their own label; a pending entry older than 60 s is ignored. A Write/Edit gate decision is unchanged. A manifest test asserts that PreToolUse and PostToolUse match only `Write`/`Edit` plus the subagent tool, with no wildcard. The gate entry stays at index 0 — files: src/aspark_guard/activity.py, src/aspark_guard/cli.py, hooks/hooks.json, tests/test_activity.py, tests/test_install.py |
| T9 | NFR-2 privacy marker test across every hooked event | US-3, US-5 | AC-3.1, AC-3.2, AC-5.3, NFR-2 | T5, T7, T8 | `done` | One test feeds every new subcommand plus subagent-stop and PreToolUse with a unique marker in each content field (prompt, tool input content, subagent prompt, tool output, last assistant message, thinking, notification message). It forces a rotation, then greps `activity.jsonl`, `.1` and `activity.pending.jsonl`: 0 markers, no `str(Path.home())`, no absolute path — files: tests/test_activity_privacy.py |
| T10 | `scan` prints the activity line count and current file size | US-4 | AC-4.7, NFR-5 | T4 | `done` | `guard.py scan` on a project with a log prints `activity lines:` (current + rotated) and `activity size:` next to the ledger and run counts, and still creates no file (`tree()` unchanged). With no log it prints 0 — files: src/aspark_guard/cli.py, tests/test_activity.py |
| T11 | README: records section, reader contract, config, invariants, limits | US-3, US-1, US-2, US-4 | AC-3.4, AC-1.4, AC-1.7, AC-2.6, AC-4.5, AC-4.6, NFR-7 | T5, T7, T8 | `done` | The README lists every activity event and field with an example line, and says "metadata only, never content" and that the activity files are local and git-ignored while ledger and trail stay committable. The union-merge advice names only `ledger.jsonl` and `trail.jsonl`, and so does the repo's own `.gitattributes`. It documents: `waiting` may outlive the answer; no `ended` = possibly killed, staleness is the reader's call; the `v` meaning; `"activity"` in the config block; the hook count; the measured line count replacing "under a thousand" (ruling Q2); `activity.py` in the module list; the POSIX limit now resting on `fcntl` — files: README.md, .gitattributes |
| T12 | NFR-1 benchmark, full suite, line count, evidence record | US-4 | NFR-1, NFR-6, NFR-7, AC-4.8 | T9, T10, T11 | `todo` | `tests/bench_hooks.py` runs 50 invocations per new hook and records p95 ≤ 100 ms and max ≤ 500 ms, with and without `.spark/` and at the 2 MB cap. Gate and ledger hooks stay within 50 ±10 ms. `docs/evidence.md` §8 holds the numbers, the command and the `wc -l src/aspark_guard/*.py` count, which matches the README (ruling Q2). The README cost section states the added cost per prompt and per subagent in projects without `.spark/`. The full suite is green, and the only edited existing assertion is `EXPECTED_EVENTS` (ruling Q1) — files: tests/bench_hooks.py, docs/evidence.md, README.md |

**T1 outcomes: what happens to the plan.** Any Degrade on a **Must** AC means `/increment` STOPs after T1. The PO amends the spec (A3: "amended before build"), and this plan is revised in place before T2.

| If T1 finds… | Affected | Plan response |
|---|---|---|
| UserPromptSubmit or Stop not delivered to plugin hooks | AC-1.1/1.2, all of US-1 | STOP. Without them US-1 has no basis → PO re-scopes |
| SubagentStart missing | AC-2.1, 2.2, 2.3, all of US-5 | `agent_run` only, always `duration_ms:null` (AC-2.4 path). T6 and T8 are dropped. Spec amendment |
| `agent_id` differs between Start and Stop | AC-2.2/2.3 | Pair by `session_id`+`agent_type` only when exactly one start is open, otherwise `null`. Spec amendment |
| Notification lacks a type field that tells a prompt from an idle reminder | AC-1.3 | Use PermissionRequest for `waiting/permission` if it exists, otherwise write no `waiting` at all, because C12 forbids guessing. Spec amendment |
| AskUserQuestion fires no distinguishable notification | AC-1.3 `question` | Only `permission` is recorded. The README says a question shows as `idle` after Stop. Still in spec (reasons are "e.g.") |
| Permission notification arrives > 2 s after the prompt appears | AC-1.3 timing | Record the measured latency in the evidence file and hand it to the PO. Don't try to beat it with tool hooks (C4) |
| SessionEnd missing | AC-1.5, AC-2.6 first clause | Every session looks killed. Spec amendment |
| No short description in the subagent tool's input | US-5 (Should) | `task` is always `null` (AC-5.2 path). T8 shrinks to a manifest-free no-op and is closed as descoped |

## 4. Test Strategy

- **Unit (`cli.main` via `GuardTestCase.run_hook`, the house style):**
  - US-1: state lines per event, allowlists, the idle reminder staying silent, two sessions.
  - US-2: start, pairing, resume, null duration, no `stop_reason`, a trail golden line.
  - US-5: sanitising and the exactly-one pairing.
  - US-4: config switch, `scan`.

  Fixtures come from T1's real payload shapes (NFR-6), not from the docs.
- **Integration (real processes):**
  - `test_install` runs every new manifest command through a shell from a path with a space.
  - The negative case and fail-open cover each new subcommand (AC-4.1, 4.2, 4.4).
  - NFR-4 concurrency uses 2 subprocess writers × 500 events across a real 2 MB rotation, plus the truncated-tail case.
  - AC-3.3 runs a `git status --porcelain` check in a `git init` temp repo.
  - NFR-2 is a marker test across every event, the rotated file and the pending file.
- **Benchmark (T12, not in `discover`):** NFR-1 p95 and max over 50 runs per hook, in three setups: with `.spark/`, without it, and at the cap. The result goes in `docs/evidence.md`, with the command next to it.
- **Deliberately left to `/demo-day`:** one full loop in `aspark-vscode` with the plugin installed from a local build. It covers:
  - success signals 1–2 (starts and finishes match the Claude UI, durations within ±1 s of the transcript, 5 permission prompts show `waiting` within 2 s, no session left `busy`);
  - signal 3 (`git status` after the loop);
  - NFR-5 (`scan` shows the log growing).

  These need a live harness and the author's notes. No automated test can reproduce them, which is why they are manual.
- **Regression:** the existing 142 tests stay green. The only edit to an existing assertion is extending `EXPECTED_EVENTS` (ruling Q1, logged at `/peer-review`). Ledger and trail formats are pinned by T7's golden test.

## 5. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| A3: one or more hooks are missing, or carry other fields | A Must AC can't be met as written | T1 goes first, with a pre-agreed degradation table (§3). A Must degradation stops the build until the spec is amended |
| My unverified expectations shape the design: Notification type values like `permission_prompt`, `idle_prompt`; SubagentStart without a description; subagent tool named `Task` or `Agent` | Rework of T5 and T8 | These are written as hypotheses, and no hooks reference was supplied (Q3). T1 records the facts, and T5 and T8 build from the fixtures |
| Some T1 checks need an interactive session that only the author can drive | The spike stalls in `/increment` | T1's DoD lists the interactive steps explicitly. The developer prepares the probe, and the author runs about a 10-minute script |
| flock contention or a stale lock | A hook waits until the deadline, or a line is dropped | 500 ms deadline, then drop the line silently. flock is released by the kernel when the process exits, so it can't go stale |
| The 4 MB scan on SubagentStop breaks NFR-1 at the cap | p95 > 100 ms | Substring pre-filter. T12 measures at the cap. The fallback is to scan the current file backwards and read `.1` only if nothing matched |
| Five new hooks add about 50 ms each in every project, including those without `.spark/` | Users pay a cost they didn't ask for | This is spec-accepted. The idle-reminder matcher avoids needless runs. T12 measures the cost and the README states it |
| The label pending file gives a wrong pairing when a subagent starts without a PreToolUse (another launch path) | A wrong `task` (AC-5.4) | Exactly-one rule plus the 60 s window. If T1 shows a `tool_use_id` or description on SubagentStart, the pending file goes away |
| `feature` inference is wrong across two features (A5, inherited) | A misattributed run | Accepted in the spec. The same heuristic as the trail, documented |
| The line-count claim is already false (1,533 before this feature, about 1,800 after) | NFR-7, and auditability | Ruling Q2: T11 and T12 state the measured number in the README and the evidence file |

---

## ✅ PLAN GATE

*All boxes checked → `/increment` may start. Any box open → back to `/sprint-plan`.*

- [x] Spec status is `approved` (never plan against a draft)
- [x] Architecture decision includes rejected alternatives (a decision without alternatives is a guess)
- [x] Architecture respects the constitution's technical constraints (no constitution exists. The README invariants were treated as binding: stdlib only, no new subprocess, silent, fail-open, 5 s timeout, nothing written outside `.spark/`. Both conflicts were resolved by the user: `EXPECTED_EVENTS` (Q1a) and the line count (Q2a))
- [x] Every task maps to a user story — no orphan tasks, no story without tasks (US-6 and US-7 are Won't and have no tasks, on purpose)
- [x] Every Must AC and every applicable NFR is covered by at least one task (NFR-3 is N/A per the spec)
- [x] Every task has a checkable definition of done
- [x] Task order respects dependencies
- [x] Test strategy covers every Must story
- [x] Line budget respected: Ist ~170 / Soll ~300 (excluding HTML comments)
- [x] Status set to `approved` by the user (2026-09-22)

## Deviations

Recorded during `/increment`. Evidence: `docs/evidence.md` §7.

- **D-T1-1 (user ruling, 2026-09-22): `waiting/permission` comes from `PermissionRequest`, not `Notification`.** T1 measured `notification_type: permission_prompt` 5.98 s after the dialog, and not at all for prompts answered within ~6 s, so AC-1.3's 2 s bound fails on `Notification`. `PermissionRequest` fires when the dialog is raised. The handler writes `waiting/permission` and never emits a decision (stdout stays empty, so the harness's own dialog is unaffected). `Notification` is not hooked this cycle, which also keeps `idle_prompt` out by construction (AC-1.3 idle case). Affects D2, T5 (`notification` handler → `permission-request` handler; fixture `permission_request.json`), T9 (marker in `tool_input`/`permission_suggestions`).
- **D-T1-2 (user ruling, 2026-09-22): no `waiting/question` this cycle.** `AskUserQuestion` could not be observed (unavailable in `-p`; not called interactively). AC-1.3 lists reasons as examples, so no Must is lost. T11's README states that a question to the user is not shown as `waiting`.
- **D-T1-3: `SessionEnd` reason allowlist = {`clear`, `prompt_input_exit`, `logout`, `other`}**, the harness's own values; anything else maps to `other` (T5).
- **D-T1-4: `SubagentStop` with an empty `agent_type` writes no `agent_run`.** T1 saw three such stops from harness-internal agents, none preceded by a start. Same rule the trail already applies (T7 DoD gains this case, fixture `subagent_stop_internal.json`).
- **D-T1-5: new code must run on Python 3.9.** The hooks run under the machine's `/usr/bin/python3` (3.9.6 here); `src/` already uses `from __future__ import annotations`, `activity.py` follows it. The suite itself needs ≥ 3.10 (`str | None` in test signatures) and is run with Python 3.13, as in §1 of the evidence.
- **D-T7-1: the stop time is taken on hook entry, and timing tests compare against the measured gap.** Taking it after the trail write and the scan added their cost to every run (60 ms seen). On the dev machine (dual-core i5, load average 13–56) a planned `sleep` overshoots by up to ~80 ms, so the ±50 ms check compares `duration_ms` with the real gap between the start line's `ts` and the stop call, not with the sleep.
- **D-T8-1: the `Agent` matcher carries no `statusMessage`.** Copying the gate entry whole would show "Checking SPARK gate…" on every subagent launch, which checks no gate. The command is identical, so `hook_commands()` stays valid.
- **T1 DoD gaps, accepted:** the screen-vs-hook latency for 5 permission prompts was not clocked (no screen timer); `PermissionRequest` is the earliest signal the harness offers. The `AskUserQuestion` notification type is unobserved (D-T1-2). The subagent tool name is `Agent`.
