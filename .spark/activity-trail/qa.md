# QA Report: activity-trail

| | |
|---|---|
| **Phase** | Review (hands-on) |
| **Owner** | QA Tester (`/demo-day`) |
| **Input** | Declared method (constitution §8), `.spark/activity-trail/spec.md` |
| **Status** | `failed` |
| **Round** | 1 |
| **Date** | 2026-09-23 |

<!-- Handoff: read this block first, the numbered sections below by exception. Whoever
     writes to this report updates it in the same edit that closes or re-rules a bug:
     overwrite in place, never append. The block holds one current state, never a
     per-round log; a stale block is a defect, not a cosmetic issue. -->

**Handoff**
- **Status:** `failed` — all ACs verified (headless, hook-level, and two interactive sessions by the user). Must AC-2.2 and success signal 1 fail on B4.
- **Verdict:** not demo-ready: one subagent run can produce two `agent_run` lines, the first too early and with a wrong duration (B4). Everything else holds.
- **Open:** `4 open` — Blockers: none; Majors: `B4` (Minors: B1, B2, B3, see §3)
- **Binding ruling:** §5 Verdict and the gate checklist below — the only binding location; there is no other round to point to
- **On conflict:** the numbered body below wins for everything except `Status`; log the mismatch as a finding at the next `/demo-day` and proceed — don't stop on it.

## 1. Test Environment

- **Method:** constitution §8 (Browser-observable surface `no`; substitute: live Claude Code session with the plugin from the working tree, evidence read from the guard's own files). App URL, browser, viewport: `N/A` per §8.
- **Versions:** Claude Code 2.1.280 · `/usr/bin/python3` 3.9.6 · guard `feat/activity-trail` @ `7d10577` (clean tree) · model `claude-sonnet-5`.
- **One copy only:** `aspark-guard@aspark` shows `✘ disabled`; debug log confirms the cached copy "will NOT register", the working tree's hooks do.
- **Test data:** throwaway repo `scratchpad/qa-activity-trail` (recreated from scratch: the interrupted run had left `.guard/` files), 1 commit, `.spark/weekly-stats/spec.md` (approved). Negative repo `scratchpad/qa-nospark`. Hook-level repos `scratchpad/hl/*`, driven by `hook.py`, which pipes payloads into the `hooks.json` command line through `/bin/sh` with `CLAUDE_PLUGIN_ROOT` set.
- **Headless runs (`claude -p --plugin-dir …`):** R1 prompt→stop · R2 2 parallel launches with descriptions, subagent_type omitted, plus a SendMessage resume · R3 single, type explicit · R4 single, type omitted · R5 2 parallel, type explicit · R6 a subagent writes the first artifact `.spark/qa-feature/spec.md`, then a second subagent · R7/R8 `activity:false` / `enabled:false` · R9 2 sessions at once · R10 `kill -9` during a subagent, then R11 a later session · R12 `--debug hooks` Read+Bash · R13 repo without `.spark/`.
- **Interactive (the user, `claude --plugin-dir … --model claude-sonnet-5`):** I1 `537e669d…` (08:37): 5 auto-approved `sleep 1 && echo …` (no dialog: step-list error), one Agent launch, idle ≥ 2 min, two extra short prompts, `/clear` → I2 `66096455…`, `/exit`. I3 `6424d2c7…` (08:42): 5× `touch qaN.txt`, each a real permission dialog answered Yes, `/exit`. The user noted no wall-clock times. Timing is taken from transcript `tool_use`/`tool_result` timestamps (content not read).

## 2. Acceptance Criteria Verification

| Spec ID | Steps performed | Expected | Observed | Result |
|---|---|---|---|---|
| AC-1.1 | R1–R13, each prompt | one `busy/prompt` per prompt | each session's first line e.g. `"reason": "prompt", …"e1714e87…", "state": "busy", "ts": "…08:04:28.905Z"` | ✅ pass |
| AC-1.2 | R1–R11; R9 session P's turn ended while its subagent ran | `idle/stop`; running run not closed | P: `idle/stop` 08:13:00.197, then `agent_run af7ab… duration_ms 4647` at 08:13:02.729 | ✅ pass |
| AC-1.3 | I3: 5 dialogs; hook-level markers; I1 idle 08:37:39.880 → next prompt 08:39:47.635 (127 s) | `waiting/permission` ≤ 2 s, no text; idle reminder writes nothing | tool_use → `waiting/permission`: 05.551→06.222, 58.880→59.157, 42.385→42.724, 44.878→45.135, 47.008→47.364 (0.26–0.67 s; a dialog can't appear before its tool_use, so latency ≤ gap). 0 `QAMSG` hits. No line during the 127 s idle, which is longer than the ≥ 60 s reminder (evidence §7, T1) | ✅ pass |
| AC-1.4 | I3; README 279–282 | next event supersedes `waiting`; stale `waiting` documented | after the 5th answer `idle/stop` 08:45:49.209 supersedes; between answer 1 (result 08:43:57.388) and the next dialog `waiting` stayed on, as documented | ✅ pass |
| AC-1.5 | I1 `/clear`; I2, I3 `/exit`; headless exits | `ended` | `"reason": "clear", …"537e669d…", "state": "ended"` 08:40:30.666; `prompt_input_exit` 08:40:42.939 (I2), 08:46:12.801 (I3); headless `ended/other`. Closing the window: not tested | ✅ pass |
| AC-1.6 | R9: two `claude -p` in parallel, same repo | lines per `session_id`, in order, not mixed | `5b93bc17…`: busy, start, idle, run, busy, idle, ended; `94751174…`: same sequence, interleaved in file, clean per filter | ✅ pass |
| AC-1.7 | R10 `kill -9` after `subagent_start`; R11 full session afterwards; README 283 | no line for killed session; README note | `f2265149…` keeps 2 lines (busy, start `a5e6102b…`), no `ended`/`abandoned`; hook-level same; README "may have been killed" | ✅ pass |
| AC-2.1 | R6 | `feature` null before any write, then inferred like trail | first start `feature: null`; after the write `a473d89b… feature: "qa-feature"`, trail says `qa-feature` | ✅ pass |
| AC-2.2 | R2, R3, R5, R6, R9 `duration_ms` vs ts gap; I1 Agent launch | one `agent_run`, same id/type/feature, ±50 ms | headless: 2273/2263, 2653/2639, 2765/2751, 5076/5060, 15089/15063 ms (≤ 26 ms off). Same-feature: the first-artifact run keeps its start's `feature: null` (trail `qa-feature`; A5). **I1: two lines for `a71b6de9…`**: `duration_ms 1678` at 08:37:27.183 and `duration_ms: null` at 08:37:37.798 (B4) | ❌ fail |
| AC-2.3 | R2 SendMessage resume of `a6e60cd3…` | second run only | 2nd start 08:04:58.170, run `duration_ms 1521` (first run 2263) | ✅ pass |
| AC-2.4 | hook-level, not live: SubagentStop with no start | run written, `null` | `aNOSTART … "duration_ms": null` | ✅ pass |
| AC-2.5 | all 65 live lines; hook-level stop with `stop_reason: end_turn` | null or absent | key absent in every line | ✅ pass |
| AC-2.6 | R10/R11 (killed half); README 283–285 (ended half) | no synthetic finish | open start `a5e6102b…` stays open; no guard-written finish. Unfinished-then-`ended` not produced live, reader contract in README | ✅ pass |
| AC-2.7 | trail after all runs vs pre-feature line in `aspark-vscode` | unchanged format | same keys, order, `ts` second resolution, `stop_reason: null`; 13 trail lines for 13 runs (incl. R7 with activity off) | ✅ pass |
| AC-3.1 | markers in prompt, subagent prompts, resume message, Write content (live) and all hook payload fields | 0 hits | `grep -c QAMARK` → 0 in `activity.jsonl`, `.pending`, `.lock`; hook-level 0 | ✅ pass |
| AC-3.2 | grep live files; hook-level description with `/Users/…` and `~/…` | no absolute path | no `/Users/`, `/private/` in activity files; label → `Review <path> and <path> …` | ✅ pass |
| AC-3.3 | `git status --porcelain --untracked-files=all` after R1–R13 | activity files hidden, ledger/trail visible, nothing outside `.spark/` | only `ledger.jsonl`, `trail.jsonl`, `qa-feature/spec.md`; `.gitignore` = `/.gitignore` `/activity*` | ✅ pass |
| AC-3.4 | README 244–297, 344; `.gitattributes` | events/fields, "metadata only", local, union-merge only committed logs | all present; union-merge names ledger and trail only | ✅ pass |
| AC-4.1 | R13 live; hook-level all 8 subcommands without `.spark/` | no file, no output, exit 0 | exit 0, stderr 0 bytes, `git status` empty, tree unchanged | ✅ pass |
| AC-4.2 | hook-level stdout of every new subcommand | empty | `stdout=''` for all (incl. user-prompt-submit, permission-request) | ✅ pass |
| AC-4.3 | hook-level, not live: 2 MB prefill + old `.1` | rotate, one generation, no split | current 1 line/126 B, `.1` 16385 lines, old gen gone, 0 unparsable; pairing across `.1` works (`aROT1 duration_ms 461`) | ✅ pass |
| AC-4.4 | hook-level, not live: `.guard/` 0555, truncated tail, 4 malformed payloads × 7 subcommands, lock held | exit 0, gates unchanged | all exit 0, silent; Write plan on draft spec → same `deny` with activity on/off and under lock; truncated line followed by a parseable line | ✅ pass |
| AC-4.5 | R7 `{"activity": false}`, R8 `{"enabled": false}`, README 297/363 | nothing appended; documented | 38 → 38 lines both times; trail still grew | ✅ pass |
| AC-4.6 | all 65 live lines; README 285 | `v` on every line, meaning documented | `v: 1` everywhere | ✅ pass |
| AC-4.7 | `guard.py scan .` | activity count and size | `activity lines: 65 (current + rotated)`, `activity size: 12073 bytes (rotates at 2097152)`; exit 0 | ✅ pass |
| AC-4.8 | R12 `--debug hooks`: Read and Bash calls | no hook invocation | `tool_dispatch_start/end` for Read and Bash with no command hook between; only SessionStart, UserPromptSubmit, Stop, SessionEnd ran | ✅ pass |
| AC-5.1 | R3, R5, R6 (type explicit); R2, R4 (type omitted) | description → `task` ≤ 80 chars | explicit: labelled. Omitted: `task: null` although one launch with a description (B1); hook-level 80 chars, no control chars | ❌ fail (Should) |
| AC-5.2 | hook-level, no description; R2 resume | `null` | `null` both | ✅ pass |
| AC-5.3 | markers in subagent prompts R2–R6 | 0 hits | 0 | ✅ pass |
| AC-5.4 | R5 two parallel launches, type explicit | each label on its own id | `a97fa47c…` → "QA parallel alpha", `af37aae1…` → "QA parallel beta", as the model reported | ✅ pass |
| NFR-4 | hook-level: 2 writers × 500 events through the manifest command, 2 MB − 50 KB prefill | 0 lost, 0 unparsable, across rotation | 16984/16984 lines, W1 500, W2 500, 0 unparsable, rotated; truncated tail case above | ✅ pass |
| NFR-5 | `scan` with log present and with `activity:false` | scan shows whether the log is written | counts shown; the switch state is not (B2) | ✅ pass (B2) |
| Signal 1 | log vs the subagent's own transcript, first → last timestamp (the user noted no UI duration) | 1 start + 1 finish, ±1 s | 11 single runs within 384 ms (e.g. `af37aae1…` 5053/5060, `afbfc81a…` 15447/15063). `a71b6de9…`: transcript 12397 ms vs logged 1678 ms plus a 2nd finish (B4) | ❌ fail |
| Signal 2 | I3 dialogs; last line of every session | `waiting` ≤ 2 s on 5 dialogs; none left `busy` | 5/5 ≤ 0.67 s after tool_use; every session ends `idle` then `ended` | ✅ pass |
| Signal 3 | `git status --porcelain --untracked-files=all` after I1–I3 | no activity file; ledger/trail visible | `ledger.jsonl`, `trail.jsonl`, `qa-feature/spec.md`, and the user's `qa1–5.txt` only | ✅ pass |

NFR-1, -2, -6, -7 are verified at /peer-review (spec §5), NFR-3 is N/A. Observed in passing: live NFR-2 markers 0 (AC-3.1).

## 3. Exploratory Findings

| # | Severity | Steps to reproduce | Expected vs. observed | Status |
|---|---|---|---|---|
| B1 | Minor | Throwaway repo, `claude -p '…launch one subagent with the Agent tool, do NOT pass subagent_type, description "QA single omitted"…' --plugin-dir …`, then read `activity.jsonl` and `activity.pending.jsonl` | Expected `task: "QA single omitted"` (one launch, AC-5.1, README 267–271). Observed `subagent_start … agent_type "general-purpose", task: null`; pending holds `"agent_type": null, "task": "QA single omitted"`, unclaimed. Same launch with `subagent_type` set (R3) is labelled | open |
| B2 | Minor | Write `.spark/guard.json` `{"activity": false}`, run `guard.py scan .` | Expected scan to show the log is off (NFR-5: scan is the one place to see it). Observed `enabled: True (ledger=True, drift=True)` plus old counts; no `activity=` flag, so "off" and "silently failing" look the same | open |
| B4 | Major | Interactive session in the throwaway repo; prompt Claude to start one general-purpose subagent (description "QA interactive") that answers OK. Here the harness added a meta message to the subagent at 08:37:26.896, right after its first answer, and the subagent worked on until 08:37:37.470 (its own transcript, types and timestamps only) | Expected one `agent_run` at the end, duration ≈ 12.4 s. Observed two SubagentStops for one launch: `agent_run duration_ms 1678` at 08:37:27.183 (run still going) and `agent_run duration_ms null` at 08:37:37.798; `trail.jsonl` also got 2 lines. The cockpit shows the run finished 10 s early with a wrong duration. Fires only when the harness continues a subagent after its first stop; not seen in 13 headless launches | open |
| B3 | Minor | Hook-level: pipe `{"session_id": 5, "cwd": "<repo>", …}` into user-prompt-submit / stop / permission-request / session-end | Expected no line or a line with a usable id (scope rule: every line names its session). Observed `"session_id": null` lines (busy, idle, waiting, ended). Needs a harness payload bug to happen | open |

## 4. Console & Network

No browser, so no console or network (§8). Hook stderr: empty in every run. Harness: `R10` without a prompt argument (my mistake, `--allowedTools` swallowed it) wrote a lone `ended/other` line, which is a fact, not a defect. Timing seen while testing (NFR-1 is not QA-owned): 181–352 ms per hook on this loaded machine; 692 ms for one Stop under a held lock (the 500 ms deadline plus interpreter start), line dropped silently as the README says.

## 5. Verdict

Would I demo this now? No. Session state is solid: permission `waiting` lands 0.26–0.67 s after the tool call, idle reminders write nothing, `/clear` and `/exit` give the right `ended` reasons, and concurrency, rotation, kill, privacy and fail-open all hold. But one interactive subagent run produced two finish lines, the first 10 s early with a duration of 1.7 s for a 12.4 s run (B4). That breaks Must AC-2.2 and success signal 1, which is exactly the "how long did it run" answer the cockpit exists for. B4 goes back to `/increment` (for example: pair a stop only with an open start, and decide what a second stop of the same run means). B1–B3 are Minor and need the user's decision.

---

## ✅ QA GATE

- [ ] Every Must-story acceptance criterion verified by the declared method and passed (all verified; AC-2.2 fails, B4)
- [x] Every QA-owned NFR verified and passed (NFR-4, NFR-5)
- [ ] No open Blocker or Major bugs (B4 Major open; Minors B1–B3 await the user's decision)
- [x] Hook stderr free of errors on the tested flows (no browser console, §8)
- [x] Tested on all agreed viewports: N/A (§8, no browser surface); headless and interactive sessions both run
- [x] Line budget respected: Ist 99 / Soll ~130 (excluding HTML comments)
- [ ] Status set to `passed`
