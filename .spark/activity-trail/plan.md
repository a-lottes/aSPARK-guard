# Plan: activity-trail

| | |
|---|---|
| **Phase** | Plan |
| **Owner** | Engineering Manager (`/sprint-plan`) |
| **Input** | `.spark/activity-trail/spec.md` (must be `approved`) |
| **Status** | `approved` |
| **Date** | 2026-09-23 (revised after `/demo-day` round 1; first approved 2026-09-22) |

<!-- Handoff: read this block first, the numbered sections below by exception. Whoever
     writes to this plan updates it in the same edit that changes a task's status or
     the plan's own status: overwrite in place, never append. The block holds one
     current state, never a per-round log; a stale block is a defect, not a cosmetic
     issue. -->

**Handoff**
- **Status:** `approved` — revised in place 2026-09-23 after `/demo-day` round 1 (`qa.md` failed: B4 Major; B1, B2 Minor; B3 accepted as is by the user, no task) against the spec re-approved the same day (C14–C16); revision re-approved by the user 2026-09-23. User rulings at re-approval: `v` stays 1; T17 also corrects the README's stale "142 tests" status line. T1–T12 stay `done`; T13–T17 are new. Next step: `/increment` from T13.
- **Summary:** New module `activity.py` appends v1 metadata-only lines to `.spark/.guard/activity.jsonl` from one subcommand per new hook. A run's duration is paired when the line is written, by scanning the log itself: **every finish pairs with its agent's latest start, so the last stop wins (C14)**. Every append and the single 2 MB rotation run under an `fcntl.flock`. A self-ignoring `.spark/.guard/.gitignore` keeps `activity*` out of git.
- **Open:** `none` — T1–T17 done. Next: `/peer-review` (re-review of T13–T17), then `/demo-day` re-test. Carried to `/peer-review`: `EXPECTED_EVENTS` edit (ruling Q1). NFR-1 as amended (C15) is closed by T17, not by T12's deviation.
- **Binding ruling:** §3 Task Breakdown for current task status; a plan revision after review/QA findings updates §1/§3 in place, never a new section
- **On conflict:** the numbered body below wins for everything except `Status`; log the mismatch as a finding at the next `/peer-review` and proceed — don't stop on it.

<!-- Budget: ~300 lines. -->

## 1. Architecture Decision

- **Context:** The guard is a single-entry Python stdlib plugin (`bin/guard.py` → `cli.main`, one subcommand per hook). It must be fail-open and silent without `.spark/`, and it already appends JSONL with `ledger.append_to`. Today it hooks PreToolUse/PostToolUse (Write/Edit), SubagentStop and SessionStart. The spec adds session state and subagent runs. These need five hook events (UserPromptSubmit, Stop, Notification, SubagentStart, SessionEnd) that the guard has never used and that are unverified against the installed harness (A3). It also needs a start→finish pairing with ±50 ms precision, a 2 MB rotation that holds up under concurrent writers, and an ignore rule written from inside `.spark/.guard/`. Two facts inherited from the codebase: `src/` is already **1,533 physical lines**, so the README's "under a thousand" claim is already false (NFR-7). And `ledger.utc_now()` has 1 s resolution. **Revision 2026-09-23:** `/demo-day` found that the harness can send SubagentStop twice for one run with no start in between (B4, A8). The T7 pairing gave the first stop 1678 ms of a 12.4 s run and the second `null`. Also, an `Agent` launch without `subagent_type` loses its label (B1), and `scan` doesn't show whether activity is switched on (B2). The constitution is now active: Python 3.9 runtime and ≥ 3.10 for tests, no numeric latency bar, and the `cli` lens binds `scan`.
- **Decision:** Add one module, `src/aspark_guard/activity.py`, with one `cli.py` handler per new event, in the house style. The file is append-only, and only facts go into it. Details:
  - **D1 Line format v1.** Every line has `v` (1), `ts` (UTC ISO with ms, `2026-09-22T10:00:00.123Z`), `event` and `session_id`. The per-event fields are:
    - `session_state`: `state`, `reason`.
    - `subagent_start`: `agent_id`, `agent_type`, `feature`, `task`.
    - `agent_run`: `agent_id`, `agent_type`, `feature`, `duration_ms`.

    `stop_reason` is **absent** (AC-2.5). No field holds a path, so AC-3.2 holds because nothing path-shaped is recorded, and the NFR-2 test proves it. Keys are sorted, the same as ledger and trail. `ledger.utc_now` stays untouched, so the ledger and trail byte format does not change.
  - **D2 Reasons are drawn from fixed allowlists, never copied from the payload.**
    - UserPromptSubmit → `busy/prompt`.
    - Stop → `idle/stop`.
    - Notification → `waiting/permission` or `waiting/question`, keyed only on the payload's type field. `message` is never read. The hooks.json matcher is limited to those types, so idle reminders never start the guard at all (AC-1.3, C12). *(Superseded by D-T1-1: `waiting/permission` comes from PermissionRequest.)*
    - SessionEnd → `ended/` plus one of {`clear`, `logout`, `exit`, `other`}. *(Values per D-T1-3.)*
  - **D3 Pairing happens when the finish line is written; the last stop wins (C14).** On SubagentStop the guard reads `activity.jsonl.1` (if present) and then `activity.jsonl`, in that order. Raw lines are pre-filtered by an `agent_id` substring check before any JSON parsing, so a 4 MB scan stays cheap.
    - Every finish pairs with the **latest `subagent_start` of that session and `agent_id`**, whether or not an `agent_run` already follows it. In `_scan_agent` this means an `agent_run` no longer resets the open start.
    - So a second SubagentStop of one run (A8) is measured from the same start (AC-2.2). A resume always brings its own start, so it measures only its own run (AC-2.3).
    - The duration is the stop time taken on hook entry (D-T7-1) minus the start's `ts`, in ms. If neither generation holds a start, every finish gets `duration_ms: null` (AC-2.4).
    - Lines already written are never touched. The reader picks the authoritative finish (D8, AC-2.8). The trail keeps writing one line per stop (AC-2.7).
    - The same scan also returns `seen`: whether this agent has *any* line (start or run) in this session. The new pairing doesn't change it. `seen` is what stops a resumed start from claiming a label parked for a new launch (review F3, D6), and a double stop adds only `agent_run` lines, so a resume after it is still `seen`.

    There is no second source of truth.
  - **D4 One locked write path, activity only.**
    - The guard takes `fcntl.flock` on `.spark/.guard/activity.lock`, using non-blocking retries with a 500 ms deadline. If the deadline passes it drops the line silently (fail-open).
    - It then appends a newline if the file's last byte isn't `\n` (NFR-4, truncated tail).
    - If the size is ≥ 2 MB, it does `os.replace(activity.jsonl, activity.jsonl.1)`.
    - Then it appends one line.

    Ledger and trail keep using `ledger.append_to`, unchanged and never rotated.
  - **D5 Git.** On the first activity write, the guard creates `.spark/.guard/.gitignore` if it is absent, containing `/.gitignore` and `/activity*`. The file ignores itself, so `git status` stays clean. It never overwrites an existing file, and ledger and trail stay visible (AC-3.3).
  - **D6 Label (Should).** A second PreToolUse matcher entry for the subagent tool (`Agent`) calls the **same** `pre-tool-use` command. That keeps the gate entry at index 0 and keeps `test_install.hook_commands()` valid. The handler branches on `tool_name` before any gate logic. It stores `{t, session_id, agent_type, task}` in `activity.pending.jsonl`. `task` is the payload's short description, with control characters removed, paths masked and whitespace collapsed, cut to ≤ 80 chars, otherwise `null`. **A launch without `subagent_type` is parked as `general-purpose`**, the type the harness then reports on its SubagentStart (QA B1, runs R2/R4). The constant is `DEFAULT_SUBAGENT_TYPE` in `activity.py`. SubagentStart takes the task **only if exactly one** pending entry for that session and type is younger than 60 s, and only if the agent is not `seen` (D3). Every matching entry is used up either way, and an ambiguous match gives `null` (AC-5.4).
  - **D7 Config.** `"activity": true` goes into `config.DEFAULTS`, and the `enabled: false` gate applies to it like every other key (AC-4.5). `scan` prints the effective value in its `enabled:` line: `(ledger=…, drift=…, activity=…)` (B2, NFR-5).
  - **D8 Reader contract (README).**
    - A session's state is its latest `session_state`.
    - Any later line of that session supersedes `waiting` and means busy.
    - A missing `ended` line means the session may have been killed.
    - A run with no `agent_run` in an `ended` session is over.
    - **A run's authoritative finish is the latest `agent_run` of that session and `agent_id` after that agent's latest `subagent_start`.** A run can briefly show as finished before a later `agent_run` corrects its duration (AC-2.8).
    - `v` goes up on any change to event names, fields or their meaning. Readers refuse a `v` they don't know. C14 keeps `v: 1` (see Alternatives).
- **Alternatives considered:**
  | Alternative | Why rejected |
  |---|---|
  | Extend `trail.jsonl` with starts and durations | Spec §6 forbids it. The trail is the committed run counter, and AC-2.7 requires its bytes unchanged |
  | A state snapshot file (`activity.json` rewritten on every event), or a side index of open starts | Rewriting on every event races between concurrent sessions. A snapshot or index is a second source of truth that can drift from the log. Scanning ≤ 4 MB with a substring pre-filter is cheap (evidence §8: ≤ 16 ms p95 at the cap) |
  | Write raw start/stop only and let the consumer compute `duration_ms` | AC-2.2 puts `duration_ms` in the log. Every consumer would have to re-implement pairing, resume handling and rotation stitching |
  | Rotate with `os.replace` and no lock | Two writers that both see ≥ 2 MB rotate twice. The second rename replaces the first generation, so up to 2 MB is lost. That fails NFR-4 |
  | SQLite (stdlib) | Can't be tailed as text, and breaks the "the file is the interface" contract (A1, §6). Readers would need a driver |
  | Ignore via root `.gitignore` or `.git/info/exclude` | Writes outside `.spark/`, which breaks an existing invariant (§6, AC-3.3) |
  | A committable (non-self-ignoring) `.spark/.guard/.gitignore` | It shows up as `??` in every adopting repo and asks the user to decide something. The guard recreates it anyway, so committing it buys nothing |
  | Task label from `PostToolUse` of the subagent tool, or from `transcript_path` | PostToolUse fires only when the run is over. Reading transcripts is reading content (US-3, §6) |
  | One generic `activity` subcommand that dispatches on `hook_event_name` | Works, but breaks the codebase's one-subcommand-per-event pattern for no gain |
  | Keep pairing with open starts only (the T7 behaviour) | This is QA B4. The run's too-early first finish stands, and the real one gets `null`. The amended AC-2.2 forbids that `null` (C14) |
  | Hold back, suppress or rewrite the earlier `agent_run` when a later stop arrives, or debounce stops | Out of scope (C14). The log is append-only facts. Holding a line back needs a timer the hooks don't have, and a debounce guesses when a run is over (constitution §1.3) |
  | Bump `v` to 2 for the C14 pairing | No event, field or field definition changes. `duration_ms` is still "ms from this agent's latest start to this finish". It is now filled for a finish it used to leave `null`. AC-2.8 reads correctly on every v1 file already on disk, and a bump would make a cockpit refuse those files for nothing. **Raised for the user's confirmation** |
  | B1: let a pending entry with no type match a start of any type | If a typed launch and an untyped launch run in parallel, both entries match the typed start and both labels are lost. An untyped entry could also label a different type's start. Parking the harness's own default keeps the match exact |
- **Consequences:**
  - *Easier:* the cockpit gets one versioned, tailable file with durations already computed. The log alone is enough for pairing, so there is nothing to keep consistent. Every finish carries a duration whenever its start is in the log.
  - *Harder:*
    - Five new hook invocations per turn or subagent, paid in every project, including those without `.spark/` (evidence §8).
    - `fcntl` makes the POSIX-only limit structural.
    - `src/` grew to 2,006 lines, and the README has to state that number (NFR-7).
    - A `.gitignore` file appears under `.spark/.guard/`.
    - A reader must apply AC-2.8 instead of taking the first `agent_run`, and the cockpit may show a run finished and then correct it.
    - A resume that arrives without a start would be measured across both runs (A8, accepted in C16).
    - `general-purpose` is a harness default seen in QA. If the harness changes it, an untyped launch falls back to `task: null` (AC-5.2 path), never to a swapped label.
- **User rulings (2026-09-22):**
  - **Q1 → (a).** NFR-6 says existing tests pass "unchanged", but adding hooks means extending `EXPECTED_EVENTS` in `tests/test_install.py`. The user ruled that this is allowed, as the only edit to an existing assertion. It is logged at `/peer-review` as keeping the test's intent: every event the plugin relies on is wired.
  - **Q2 → (a).** The README's line-count claim is replaced by the number `wc -l` measures, recorded in the README (T11) and in `docs/evidence.md` (T12), as NFR-7 allows.
  - **Q3.** No hooks reference was supplied. T1 records the facts, and my field-name expectations stay hypotheses until then.
- **User rulings (2026-09-23, after `/demo-day`):** B4 → "last stop wins" (spec C14, D3/D8). B1 → fix (D6, T15). B2 → fix (D7, T16). B3 → accepted as is, no task.

## 2. Affected Components

Scoped by hand: no blast-radius tool was passed and aspark-graph is unavailable. I read every file below. For the revision I re-read `activity.py`, `cli.py` (`_scan`, handlers), `config.py`, `tests/test_activity.py`, `tests/bench_hooks.py`, the README activity and cost sections, and evidence §7/§8.

- **New:** `src/aspark_guard/activity.py` (write path, lock, rotation, gitignore, pairing, labels, allowlists). Tests: `tests/test_activity.py`, `tests/test_activity_rotation.py`, `tests/test_activity_privacy.py`. Benchmark: `tests/bench_hooks.py` (not collected by `discover`). Payload fixtures under `tests/fixtures/payloads/`, and for the revision `subagent_stop_double.json`.
- **Changed:**
  - `src/aspark_guard/cli.py`: 5 handlers, a subagent-tool branch in `handle_pre_tool_use`, an activity call in `handle_subagent_stop`, and `scan` (revision: the `enabled:` line).
  - `src/aspark_guard/activity.py` (revision): `_scan_agent` pairing, `record_pending_task` default type, docstrings.
  - `src/aspark_guard/config.py`: `activity` key.
  - `src/aspark_guard/trail.py`: `_feature_for_session` becomes public `feature_for_session`. Behaviour and output are identical.
  - `hooks/hooks.json`: 5 events plus 1 PreToolUse matcher. There are no manifest changes in the revision.
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
| T12 | NFR-1 benchmark, full suite, line count, evidence record | US-4 | NFR-1, NFR-6, NFR-7, AC-4.8 | T9, T10, T11 | `done` | `tests/bench_hooks.py` runs 50 invocations per new hook and records p95 ≤ 100 ms and max ≤ 500 ms, with and without `.spark/` and at the 2 MB cap. Gate and ledger hooks stay within 50 ±10 ms. `docs/evidence.md` §8 holds the numbers, the command and the `wc -l src/aspark_guard/*.py` count, which matches the README (ruling Q2). The README cost section states the added cost per prompt and per subagent in projects without `.spark/`. The full suite is green, and the only edited existing assertion is `EXPECTED_EVENTS` (ruling Q1) — files: tests/bench_hooks.py, docs/evidence.md, README.md |
| T13 | **B4, last stop wins:** every SubagentStop pairs with the latest `subagent_start` of its session and `agent_id` (D3). New fixture `subagent_stop_double.json`: the real SubagentStop key set from evidence §7 (`agent_id`, `agent_type: "general-purpose"`, `agent_transcript_path`, `last_assistant_message`, no `stop_reason`), redacted | US-2, US-5 | AC-2.2, AC-2.3, AC-2.4, AC-2.7, AC-5.4, NFR-6 | T12 | `done` | Tests in `TestAgentRun`. (a) One start, then the new fixture fed twice for that `agent_id` with a measured gap before each stop → two `agent_run` lines. Each `duration_ms` is within ±50 ms of its own gap from the **same** start `ts`, the second is greater than the first, and neither is `null`. (b) After the second stop, the first `agent_run` line is byte-identical to what it was before. (c) The trail gained exactly 2 lines. (d) Two stops with no start → two lines, both `duration_ms: null`. (e) start, stop, stop, start, stop → the last line is measured from the second start only. (f) A start in `.1` with both stops in the current file → both pair. (g) Both stops: exit 0 and empty stdout. In `TestTaskLabel`: after start, stop, stop, a resumed start of that id gets `task: null`, while a pending same-type launch goes to the new `agent_id` (F3 holds). Every pre-existing test in `test_activity.py`, `test_trail.py` and `test_failopen.py` passes unedited. The `_scan_agent` and `record_agent_run` docstrings state last stop wins — files: src/aspark_guard/activity.py, tests/test_activity.py, tests/fixtures/payloads/subagent_stop_double.json |
| T14 | **README reader contract for AC-2.8** (D8) | US-2 | AC-2.8, AC-2.2, AC-4.6 | T13 | `done` | In README "What it records": the `duration_ms` bullet says it is measured from the latest start of that `agent_id` in the session, for every finish after that start, and is `null` for every finish when the start isn't in the log. **Reading it** states the AC-2.8 rule word for word (latest `agent_run` of that `session_id`+`agent_id` after that agent's latest `subagent_start` is authoritative). It also states that a run can briefly show as finished before a later `agent_run` corrects its duration, and that the trail then holds one line per finish. It says `v` stays 1, and that the rule applies to every v1 file already on disk. No other README section changes — files: README.md |
| T15 | **B1:** an `Agent` launch without `subagent_type` is parked as `DEFAULT_SUBAGENT_TYPE = "general-purpose"` (D6) | US-5 | AC-5.1, AC-5.4 | T13 | `done` | Tests in `TestTaskLabel`, built on `pre_tool_use_task.json` with the `subagent_type` key deleted (and, separately, set to `""` or `null`). (a) A launch, then a start with `agent_type: "general-purpose"` → the start's `task` is the description. (b) An untyped launch plus an explicit `general-purpose` launch → both starts get `null` (exactly-one rule). (c) An untyped launch then an `aspark:product-owner` start → that start gets `null`, and a later `general-purpose` start still gets the label. The pending file holds `"agent_type": "general-purpose"` for the untyped launch, and no other field changes. The README `task` bullet adds one sentence: a launch without a type counts as `general-purpose` — files: src/aspark_guard/activity.py, tests/test_activity.py, README.md |
| T16 | **B2:** `scan` shows the activity switch in its `enabled:` line (D7) | US-4 | AC-4.7, AC-4.5, NFR-5 | T12 | `done` | Tests in `TestScan`. With no config, `scan` prints `enabled:         True (ledger=True, drift=True, activity=True)`. With `{"activity": false}` it prints `activity=False`, and with `{"enabled": false}` it prints `activity=False`, the effective value from `config.Config.activity`. The tree is unchanged in each case, and the exit code is 0. No other `scan` line changes — files: src/aspark_guard/cli.py, tests/test_activity.py |
| T17 | **NFR-1 as amended (C15), plus the closing checks for the revision.** Adds an in-process mode to the bench (this also resolves review F5) | US-4, US-2 | NFR-1, NFR-6, NFR-7 | T13, T14, T15, T16 | `done` | `tests/bench_hooks.py` gains an `inproc` mode. After import, it times each activity handler (`user-prompt-submit`, `stop`, `permission-request`, `session-end`, `subagent-start`, `subagent-stop`, and `pre-tool-use` for `Agent`) in three setups: with `.spark/`, without `.spark/`, and at the 2 MB cap. At the cap, `subagent-stop` is timed on an agent that already has start, run, run. `docs/evidence.md` gains a new dated §9. It records both bench commands, the machine and its load, the in-process median/p95/max per handler, and the interleaved before/after figures for `pre-tool-use` and `post-tool-use` versus `main`. §8 is not rewritten. §9 also records that every hook stays under the 5 s manifest timeout, and a one-line run of `subagent-stop`, `subagent-start` and `pre-tool-use` (Agent) through their manifest command lines under `/usr/bin/python3` 3.9 with exit 0 and empty stderr (constitution §4). README invariant 3 states the guard's own in-process share per activity hook, with and without `.spark/`, naming the machine and load and linking §9. The full suite is green under Python ≥ 3.10. `wc -l src/aspark_guard/*.py` equals the number in README and §9 — files: tests/bench_hooks.py, docs/evidence.md, README.md |

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
  - US-2: start, pairing, resume, null duration, no `stop_reason`, a trail golden line. The revision (T13) adds the double stop (both measured from one start, lines unchanged, two trail lines), the double stop with no start (both `null`), a resume after a double stop, and the rotated start.
  - US-5: sanitising and the exactly-one pairing. The revision (T13, T15) adds an untyped launch, an untyped launch mixed with a typed one, and F3 after a double stop.
  - US-4: config switch, `scan` (T16: `activity=` in the `enabled:` line, default, off, and `enabled:false`).

  Fixtures come from T1's real payload shapes (NFR-6), not from the docs. `subagent_stop_double.json` uses the real SubagentStop key set from evidence §7. The double-stop *sequence* is the one QA observed (I1). It can't be recorded on demand, so the test replays it.
- **Integration (real processes):**
  - `test_install` runs every new manifest command through a shell from a path with a space.
  - The negative case and fail-open cover each new subcommand (AC-4.1, 4.2, 4.4). The revision adds no subcommand, so the existing cases cover T13–T16 unchanged.
  - NFR-4 concurrency uses 2 subprocess writers × 500 events across a real 2 MB rotation, plus the truncated-tail case.
  - AC-3.3 runs a `git status --porcelain` check in a `git init` temp repo.
  - NFR-2 is a marker test across every event, the rotated file and the pending file.
  - The constitution §4 runtime check runs each changed hook subcommand once under Python 3.9 (T17).
- **Benchmark (T12, T17, not in `discover`):** per-invocation cost over 50 runs per hook in three setups (with `.spark/`, without it, at the cap), plus T17's in-process share per handler. There is no numeric bar (constitution §4, C15). NFR-1 is met by: the 5 s timeout; no hook on ordinary tool calls (AC-4.8, QA R12); no regression before vs after; and the share stated with machine and load in §9 and the README.
- **Deliberately left to `/demo-day`:** one full loop in `aspark-vscode` with the plugin installed from a local build. It covers:
  - success signals 1–2 (every run has one start and at least one finish, the **authoritative** finish is within ±1 s of the transcript, 5 permission prompts show `waiting` within 2 s, no session left `busy`);
  - signal 3 (`git status` after the loop);
  - NFR-5 (`scan` shows the log growing, and the switch).

  Round 2 re-checks:
  - B4: if the harness repeats the double stop live, the second `agent_run` is within ±1 s of the transcript. If it doesn't, the double-stop fixture is piped twice through the manifest command, labelled "hook-level, not live" (constitution §8.5).
  - B1: QA run R4 (type omitted) is labelled.
  - B2: `scan` with `activity:false`.

  These need a live harness and the author's notes. No automated test can reproduce them, which is why they are manual.
- **Regression:** the existing tests stay green. The only edit to an existing assertion is extending `EXPECTED_EVENTS` (ruling Q1, logged at `/peer-review`). No test written in T1–T12 is edited by T13–T16. Ledger and trail formats are pinned by T7's golden test.

## 5. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| A3: one or more hooks are missing, or carry other fields | A Must AC can't be met as written | T1 goes first, with a pre-agreed degradation table (§3). A Must degradation stops the build until the spec is amended |
| My unverified expectations shape the design: Notification type values like `permission_prompt`, `idle_prompt`; SubagentStart without a description; subagent tool named `Task` or `Agent` | Rework of T5 and T8 | These are written as hypotheses, and no hooks reference was supplied (Q3). T1 records the facts, and T5 and T8 build from the fixtures |
| Some T1 checks need an interactive session that only the author can drive | The spike stalls in `/increment` | T1's DoD lists the interactive steps explicitly. The developer prepares the probe, and the author runs about a 10-minute script |
| flock contention or a stale lock | A hook waits until the deadline, or a line is dropped | 500 ms deadline, then drop the line silently. flock is released by the kernel when the process exits, so it can't go stale |
| The 4 MB scan on SubagentStop grows the hook's cost at the cap | A visible share per subagent finish | Substring pre-filter. §8 measured ≤ 16 ms p95 at the cap, and T17 re-measures it after the pairing change. The fallback is to scan the current file backwards and read `.1` only if nothing matched |
| Five new hooks add one interpreter start each in every project, including those without `.spark/` | Users pay a cost they didn't ask for | This is spec-accepted. No hook on ordinary tool calls. T12/T17 measure the cost, and the README states it |
| The label pending file gives a wrong pairing when a subagent starts without a PreToolUse (another launch path) | A wrong `task` (AC-5.4) | Exactly-one rule, the 60 s window, and a `seen` agent never claims (F3) |
| A8, inherited: a resume that arrives without its own start | Its duration spans both runs | Accepted by the user (C16). QA saw a new start for every resume (R2). The README states the AC-2.8 rule, not a guarantee against this |
| The double stop can't be reproduced on demand (seen once, interactive, not in 13 headless runs) | T13 is proven only against a replayed sequence | The fixture uses the real payload shape. `/demo-day` round 2 falls back to a hook-level replay through the manifest command, and labels it as such |
| The harness changes its default subagent type from `general-purpose` | Untyped launches lose their label again | It degrades to `task: null` (AC-5.2 path), never to a swap. The constant sits next to `SUBAGENT_TOOL` with its QA source |
| A cockpit reads the first `agent_run` as final | It shows a wrong duration for a double-stopped run | D8/AC-2.8 in the README (T14). Mission Control's spec is the consumer's contract |
| `feature` inference is wrong across two features (A5, inherited) | A misattributed run | Accepted in the spec. The same heuristic as the trail, documented |
| The line-count claim is already false (1,533 before this feature, 2,006 now) | NFR-7, and auditability | Ruling Q2: the README and the evidence state the measured number, re-measured in T17 |

---

## ✅ PLAN GATE

*All boxes checked → `/increment` may start. Any box open → back to `/sprint-plan`.*

- [x] Spec status is `approved` (never plan against a draft). The spec was re-approved 2026-09-23 after amendments C14–C16.
- [x] Architecture decision includes rejected alternatives (a decision without alternatives is a guess). The revision adds four: open-start pairing, holding back or debouncing stops, a `v` bump, and a wildcard type match.
- [x] Architecture respects the constitution's technical constraints. The constitution has been active since 2026-09-23. The plan keeps Python 3.9 code with a ≥ 3.10 suite, stdlib only, no new subprocess, matchers limited to `Write|Edit` and `Agent`, no numeric latency bar (NFR-1 per C15), and the `cli` lens on `scan` (T16). Earlier conflicts: `EXPECTED_EVENTS` (Q1a) and the line count (Q2a).
- [x] Every task maps to a user story — no orphan tasks, no story without tasks (US-6 and US-7 are Won't and have no tasks, on purpose; B3 is accepted with no task)
- [x] Every Must AC and every applicable NFR is covered by at least one task (NFR-3 is N/A per the spec). AC-2.8 → T14. Amended AC-2.2/2.3/2.4/2.7 → T13. Amended NFR-1 → T17. The NFR-6 double-stop fixture → T13
- [x] Every task has a checkable definition of done
- [x] Task order respects dependencies
- [x] Test strategy covers every Must story
- [x] Line budget respected: Ist ~215 / Soll ~300 (excluding HTML comments)
- [x] Status set to `approved` by the user (first approved 2026-09-22; revision re-approved 2026-09-23)

## Deviations

Recorded during `/increment`. Evidence: `docs/evidence.md` §7.

- **D-T1-1 (user ruling, 2026-09-22): `waiting/permission` comes from `PermissionRequest`, not `Notification`.** T1 measured `notification_type: permission_prompt` 5.98 s after the dialog, and not at all for prompts answered within ~6 s, so AC-1.3's 2 s bound fails on `Notification`. `PermissionRequest` fires when the dialog is raised. The handler writes `waiting/permission` and never emits a decision (stdout stays empty, so the harness's own dialog is unaffected). `Notification` is not hooked this cycle, which also keeps `idle_prompt` out by construction (AC-1.3 idle case). Affects D2, T5 (`notification` handler → `permission-request` handler; fixture `permission_request.json`), T9 (marker in `tool_input`/`permission_suggestions`).
- **D-T1-2 (user ruling, 2026-09-22): no `waiting/question` this cycle.** `AskUserQuestion` could not be observed (unavailable in `-p`; not called interactively). AC-1.3 lists reasons as examples, so no Must is lost. T11's README states that a question to the user is not shown as `waiting`.
- **D-T1-3: `SessionEnd` reason allowlist = {`clear`, `prompt_input_exit`, `logout`, `other`}**, the harness's own values; anything else maps to `other` (T5).
- **D-T1-4: `SubagentStop` with an empty `agent_type` writes no `agent_run`.** T1 saw three such stops from harness-internal agents, none preceded by a start. Same rule the trail already applies (T7 DoD gains this case, fixture `subagent_stop_internal.json`).
- **D-T1-5: new code must run on Python 3.9.** The hooks run under the machine's `/usr/bin/python3` (3.9.6 here); `src/` already uses `from __future__ import annotations`, `activity.py` follows it. The suite itself needs ≥ 3.10 (`str | None` in test signatures) and is run with Python 3.13, as in §1 of the evidence.
- **D-T7-1: the stop time is taken on hook entry, and timing tests compare against the measured gap.** Taking it after the trail write and the scan added their cost to every run (60 ms seen). On the dev machine (dual-core i5, load average 13–56) a planned `sleep` overshoots by up to ~80 ms, so the ±50 ms check compares `duration_ms` with the real gap between the start line's `ts` and the stop call, not with the sleep.
- **D-T8-1: the `Agent` matcher carries no `statusMessage`.** Copying the gate entry whole would show "Checking SPARK gate…" on every subagent launch, which checks no gate. The command is identical, so `hook_commands()` stays valid.
- **T12 (user ruling, 2026-09-23): closed on the relative evidence; NFR-1's absolute bound stays unverified.** Carried to `/peer-review` and to a benchmark re-run on an unloaded machine. The finding: On the loaded dev machine every hook costs ~200–250 ms median, the pre-existing gate hooks included (before/after identical within noise), and a bare `python3 -c pass` alone has p95 111 ms. The activity work itself is ≤ 16 ms p95, pairing scan at the 2 MB mark included. The "gate and ledger hooks stay within 50 ±10 ms" line of the DoD can't be shown here either. Evidence §8 records all of it.
- **T1 DoD gaps, accepted:** the screen-vs-hook latency for 5 permission prompts was not clocked (no screen timer); `PermissionRequest` is the earliest signal the harness offers. The `AskUserQuestion` notification type is unobserved (D-T1-2). The subagent tool name is `Agent`.
