# QA Report: activity-trail

| | |
|---|---|
| **Phase** | Review (hands-on) |
| **Owner** | QA Tester (`/demo-day`) |
| **Input** | Declared method (constitution §8), `.spark/activity-trail/spec.md` |
| **Status** | `in-testing` |
| **Round** | 2 |
| **Date** | 2026-09-23 |

<!-- Handoff: read this block first, the numbered sections below by exception. Whoever
     writes to this report updates it in the same edit that closes or re-rules a bug:
     overwrite in place, never append. The block holds one current state, never a
     per-round log; a stale block is a defect, not a cosmetic issue. -->

**Handoff**
- **Status:** `in-testing` — round 2 complete: every AC, QA-owned NFR and success signal verified and passed at `ead7f16`, including B4's double stop seen live (I4). Awaiting the user's gate decision; the tester does not set `passed`.
- **Verdict:** demo-ready: I would demo this now.
- **Open:** `none` — B1, B2, B4 `fixed r2`; B3 `accepted` by the user.
- **Binding ruling:** §5 Verdict and the gate checklist below — the only binding location; there is no other round to point to
- **On conflict:** the numbered body below wins for everything except `Status`; log the mismatch as a finding at the next `/demo-day` and proceed — don't stop on it.

## 1. Test Environment

- **Method:** constitution §8 (Browser-observable surface `no`; substitute: live Claude Code session with the plugin from the working tree, evidence read from the guard's own files). App URL, browser, viewport: `N/A` per §8.
- **Versions:** Claude Code 2.1.280 · `/usr/bin/python3` 3.9.6 · guard `feat/activity-trail` @ `ead7f16` (clean tree) · model `claude-sonnet-5`. Spec as amended by C14–C16.
- **One copy only:** `aspark-guard@aspark` shows `✘ disabled`; debug log confirms the cached copy "will NOT register", the working tree's hooks do.
- **Test data (round 2):** fresh throwaway repo `scratchpad/qa-r2`, 1 commit, `.spark/weekly-stats/spec.md` (approved); negative repo `scratchpad/qa-r2-nospark`; hook-level repos `scratchpad/hl-r2/*` (new B4/B1/B2 cases, `cases_r2.py`) and `scratchpad/hl-r2reg/*` (all round-1 cases re-run, `cases.py`), both through the `hooks.json` command line via `hook.py`.
- **Headless runs (round 2):** Q1 untyped single launch · Q2 untyped + typed `general-purpose` in one message · Q3 background agent sent a SendMessage while running (double-stop attempt) · Q4 `--permission-mode auto` (double-stop attempt) · Q5 a subagent writes the first artifact, then a SendMessage resume · Q6 two sessions at once, each with 2 parallel typed launches · Q7 repo without `.spark/`.
- **Interactive (round 2, the user):** I4 `93e6303c…` (09:28:56–09:29:58), started with the prompt "Run `echo one` with Bash, then start one general-purpose subagent, description "QA r2 live", reply only OK"; `/exit`. The transcript holds 1 typed prompt, then 1 harness meta prompt and 1 task-notification (types and timestamps only).
- **Round-1 evidence kept where unchanged:** interactive I1–I3 (user, 08:37–08:46, repo `scratchpad/qa-activity-trail`) for AC-1.3/1.4/1.5 and signal 2; R10/R11 (live kill) and R12 (`--debug hooks`). These paths were untouched by T13–T17, and the hook-level regression re-ran them at `ead7f16`.

## 2. Acceptance Criteria Verification

| Spec ID | Steps performed | Expected | Observed | Result |
|---|---|---|---|---|
| AC-1.1 | Q1–Q7, each prompt | one `busy/prompt` per prompt | first line of every session `busy/prompt`, e.g. `605ae31e…` 09:18:10.189 | ✅ pass |
| AC-1.2 | Q3: turn ended while the background agent ran | `idle/stop`; running run not closed | `idle/stop` 09:19:32.613, then `agent_run a9f7a077… duration_ms 17409` at 09:19:45.090 | ✅ pass |
| AC-1.3 | I3: 5 dialogs; hook-level markers; I1 idle 08:37:39.880 → next prompt 08:39:47.635 (127 s) | `waiting/permission` ≤ 2 s, no text; idle reminder writes nothing | tool_use → `waiting/permission`: 05.551→06.222, 58.880→59.157, 42.385→42.724, 44.878→45.135, 47.008→47.364 (0.26–0.67 s; a dialog can't appear before its tool_use, so latency ≤ gap). 0 `QAMSG` hits. No line during the 127 s idle, which is longer than the ≥ 60 s reminder (evidence §7, T1) | ✅ pass |
| AC-1.4 | I3; README 279–282 | next event supersedes `waiting`; stale `waiting` documented | after the 5th answer `idle/stop` 08:45:49.209 supersedes; between answer 1 (result 08:43:57.388) and the next dialog `waiting` stayed on, as documented | ✅ pass |
| AC-1.5 | I1 `/clear`; I2, I3 `/exit`; headless exits | `ended` | `"reason": "clear", …"537e669d…", "state": "ended"` 08:40:30.666; `prompt_input_exit` 08:40:42.939 (I2), 08:46:12.801 (I3); headless `ended/other`. Closing the window: not tested | ✅ pass |
| AC-1.6 | Q6: two `claude -p` at once, each with 2 parallel launches | per-session lines in order, not mixed | `99ee97f6…` and `b26acab4…` each: busy, 2 starts, runs, idle…, ended; interleaved in the file, clean per filter | ✅ pass |
| AC-1.7 | round 1 R10/R11 (live kill); r2 hook-level killed case | nothing written for the killed session | r2: `KILLED` keeps its 2 lines, no `ended`/`abandoned` | ✅ pass |
| AC-2.1 | Q5: writer run, then resume | `null` before any write, then inferred like trail | 1st start `feature: null`; resume start `feature: "qa-feature"` | ✅ pass |
| AC-2.2 | hook-level: start, stop +0.3 s, stop +1.0 s; live Q1–Q6 duration vs ts gap | every finish measured from the same start, ±50 ms, never `null`; earlier lines unchanged | `aD` 488/494 then 1696/1706 ms; first line byte-identical after the 2nd stop; start in `.1` → 180/197, 883/900. Live: 2001/2009, 5268/5278, 17409/17420, 1950/1965 etc. ≤ 16 ms off, except Q1 `a4250ca5…` 2573 vs gap 2650 (77 ms: its stop line was stamped 77 ms after the duration was taken). Live double stop I4: `abe41c8b…` start 09:29:05.203 → `agent_run 1666` at 06.876 (gap 1673) and `agent_run 14083` at 19.302 (gap 14099), both from the one start | ✅ pass r2 |
| AC-2.3 | Q5 SendMessage resume; hook-level resume after a double stop | measured from latest start | live: `a0680086…` 2nd start 09:22:24.060 → `duration_ms 1337` (1st run 10702). Hook: after a double stop, resume + double stop → 654/670, 1487/1500 from the new start | ✅ pass |
| AC-2.4 | hook-level, not live: two stops, no start; another session's stop for the same id | `null` for every finish | `[null, null]`; S2's stop for `aD` → `null` (no cross-session pairing) | ✅ pass r2 |
| AC-2.5 | 62 live r2 lines; hook-level `stop_reason: end_turn` | absent | 0 lines with the key | ✅ pass |
| AC-2.6 | R10/R11 (killed half); README 283–285 (ended half) | no synthetic finish | open start `a5e6102b…` stays open; no guard-written finish. Unfinished-then-`ended` not produced live, reader contract in README | ✅ pass |
| AC-2.7 | trail after Q1–Q6, I4; hook-level double stop | format unchanged; a double finish gives 2 trail lines | same keys/format; I4 → 2 trail lines for `abe41c8b…` (09:29:06Z, 09:29:19Z); hook → 2 for `aD` | ✅ pass r2 |
| AC-2.8 | README 289–296; I4; hook-level double stop | rule stated; latest finish after latest start carries the full duration | README states the rule; I4's latest line 14083 ms vs the subagent's own transcript span 14242 ms (it answered at 06.627, got a harness meta message at 06.649, worked on to 19.034); brief "finished" 06.876–19.302 as documented | ✅ pass |
| AC-3.1 | markers in subagent prompts, Write content, resume message (Q1, Q5), hook payloads | 0 hits | 0 in `activity.jsonl`, `.pending`, `.lock` | ✅ pass |
| AC-3.2 | grep live files; hook-level description with `/Users/…` and `~/…` | no absolute path | no `/Users/`, `/private/` in activity files; label → `Review <path> and <path> …` | ✅ pass |
| AC-3.3 | `git status --porcelain --untracked-files=all` after Q1–Q6 | activity hidden, ledger/trail visible | `ledger.jsonl`, `trail.jsonl`, `qa-feature/spec.md` only | ✅ pass |
| AC-3.4 | README 244–297, 344; `.gitattributes` | events/fields, "metadata only", local, union-merge only committed logs | all present; union-merge names ledger and trail only | ✅ pass |
| AC-4.1 | Q7 live (untyped launch); hook-level 8 subcommands | no file, no output, exit 0 | exit 0, stderr 0 B, `git status` empty, tree = `README.md` | ✅ pass |
| AC-4.2 | hook-level stdout of every new subcommand | empty | `stdout=''` for all (incl. user-prompt-submit, permission-request) | ✅ pass |
| AC-4.3 | hook-level re-run at `ead7f16` | rotate, one generation | current 1 line, old `.1` replaced, 0 unparsable; pairing across `.1` 366 ms | ✅ pass |
| AC-4.4 | hook-level re-run: unwritable, truncated tail, malformed × 7, lock held | exit 0, gates unchanged | same as round 1: all exit 0 silent, `deny` identical on/off/locked | ✅ pass |
| AC-4.5 | hook-level: `activity:false`, `enabled:false`, `"nope"`, broken JSON | off → nothing; malformed → default | off/disabled write nothing; `"nope"` → default on, 1 line written | ✅ pass |
| AC-4.6 | all 65 live lines; README 285 | `v` on every line, meaning documented | `v: 1` everywhere | ✅ pass |
| AC-4.7 | `guard.py scan .` on `qa-r2` | count and size | `activity lines: 62 (current + rotated)`, `activity size: 11372 bytes …`, exit 0; `check` exit 0 | ✅ pass |
| AC-4.8 | R12 `--debug hooks`: Read and Bash calls | no hook invocation | `tool_dispatch_start/end` for Read and Bash with no command hook between; only SessionStart, UserPromptSubmit, Stop, SessionEnd ran | ✅ pass |
| AC-5.1 | Q1 untyped single; Q2 untyped + typed; hook-level untyped gp + typed PO | description → `task` | Q1 `task: "QA r2 untyped"`; Q2 both labelled; hook `aPO` → "po typed", `aGP` → "gp untyped"; pending emptied | ✅ pass r2 |
| AC-5.2 | hook-level, no description; R2 resume | `null` | `null` both | ✅ pass |
| AC-5.3 | markers in subagent prompts R2–R6 | 0 hits | 0 | ✅ pass |
| AC-5.4 | Q2, Q6 vs each agent's harness `meta.json` description; hook-level both pending before any start | own label, or `null` if ambiguous | 6/6 logged `task` equal the harness description (Q2's launches were sequential: 1st start 09:18:37.557 before 2nd tool_use 37.670). Hook: untyped + typed gp both pending → `aU null`, `aT null` | ✅ pass |
| NFR-4 | hook-level re-run: 2 × 500 events, 2 MB − 50 KB prefill | 0 lost, 0 unparsable | 16984/16984, W1 500, W2 500, 0 unparsable, rotated | ✅ pass |
| NFR-5 | `scan` with default, `activity:false`, `enabled:false`, `"nope"`, broken JSON | switch visible | `…activity=True)`, `…activity=False)`, `False (…activity=False)`, default `True` for the last two | ✅ pass r2 |
| Signal 1 | r2 log vs each subagent's own transcript (first → last); I4 | 1 start, ≥ 1 finish; authoritative finish ±1 s | 9 single headless runs: worst 904 ms (`a4250ca5…` 2573 vs 1669), others ≤ 228 ms. I4 double stop: 1 start, 2 finishes, authoritative 14083 vs 14242 ms (159 ms) | ✅ pass r2 |
| Signal 2 | I3 dialogs; last line of every session | `waiting` ≤ 2 s on 5 dialogs; none left `busy` | 5/5 ≤ 0.67 s after tool_use; every session ends `idle` then `ended` | ✅ pass |
| Signal 3 | `git status --porcelain --untracked-files=all` after I1–I3 | no activity file; ledger/trail visible | `ledger.jsonl`, `trail.jsonl`, `qa-feature/spec.md`, and the user's `qa1–5.txt` only | ✅ pass |

Carried from round 1 (code path untouched, and the r2 hook-level regression still passes): AC-1.3, -1.4, -1.5, -2.6, -3.2, -3.4, -4.2, -4.6, -4.8, -5.2, -5.3, signals 2–3. NFR-1, -2, -6, -7 are verified at /peer-review, NFR-3 is N/A.

## 3. Exploratory Findings

| # | Severity | Steps to reproduce | Expected vs. observed | Status |
|---|---|---|---|---|
| B1 | Minor | Throwaway repo, `claude -p '…launch one subagent with the Agent tool, do NOT pass subagent_type, description "QA single omitted"…' --plugin-dir …`, then read `activity.jsonl` and `activity.pending.jsonl` | Expected `task: "QA single omitted"` (one launch, AC-5.1, README 267–271). Observed `subagent_start … agent_type "general-purpose", task: null`; pending holds `"agent_type": null, "task": "QA single omitted"`, unclaimed. Same launch with `subagent_type` set (R3) is labelled | fixed r2 |
| B2 | Minor | Write `.spark/guard.json` `{"activity": false}`, run `guard.py scan .` | Expected scan to show the log is off (NFR-5: scan is the one place to see it). Observed `enabled: True (ledger=True, drift=True)` plus old counts; no `activity=` flag, so "off" and "silently failing" look the same | fixed r2 |
| B4 | Major | Interactive session in the throwaway repo; prompt Claude to start one general-purpose subagent (description "QA interactive") that answers OK. Here the harness added a meta message to the subagent at 08:37:26.896, right after its first answer, and the subagent worked on until 08:37:37.470 (its own transcript, types and timestamps only) | Expected one `agent_run` at the end, duration ≈ 12.4 s. Observed two SubagentStops for one launch: `agent_run duration_ms 1678` at 08:37:27.183 (run still going) and `agent_run duration_ms null` at 08:37:37.798; `trail.jsonl` also got 2 lines. The cockpit shows the run finished 10 s early with a wrong duration. Fires only when the harness continues a subagent after its first stop; not seen in 13 headless launches. r2: hook-level both lines measured from the one start (488, 1696 ms), never `null`; did not recur in 11 headless launches, but recurred live in I4: 2 lines (1666, 14083 ms) from the one start, never `null`, authoritative finish within 159 ms of the transcript | fixed r2 |
| B3 | Minor | Hook-level: pipe `{"session_id": 5, "cwd": "<repo>", …}` into user-prompt-submit / stop / permission-request / session-end | Expected no line or a line with a usable id (scope rule: every line names its session). Observed `"session_id": null` lines (busy, idle, waiting, ended). Needs a harness payload bug to happen | accepted |

## 4. Console & Network

No browser, so no console or network (§8). Hook stderr: empty in every r2 run. Timing seen (NFR-1 is not QA-owned): 157–248 ms per hook; 686 ms for a Stop under a held lock, line dropped silently as documented. Q1's stop line was stamped 77 ms after its duration was taken; the duration was within ±1 s of the transcript.

## 5. Verdict

Would I demo this now? Yes. B4 was seen live again in I4, in the same way as round 1: the harness reported the subagent finished, sent it a hidden message, and reported it finished again 12.4 s later. The log now carries a duration on both finishes, measured from the one start (1666 ms, then 14083 ms). The authoritative finish is 159 ms off the subagent's own transcript, and the README tells the reader which finish counts. B1 and B2 are fixed as seen, and every round-1 regression case still passes, headless and hook-level. B3 stays accepted. Status stays `in-testing` until the user closes the gate.

---

## ✅ QA GATE

- [x] Every Must-story acceptance criterion verified by the declared method and passed (AC-2.2 incl. the live double stop, I4)
- [x] Every QA-owned NFR verified and passed (NFR-4, NFR-5)
- [x] No open Blocker or Major bugs (B1, B2, B4 `fixed r2`; Minor B3 `accepted` by the user)
- [x] Hook stderr free of errors on the tested flows (no browser console, §8)
- [x] Tested on all agreed viewports: N/A (§8, no browser surface); headless and interactive sessions both run
- [x] Line budget respected: Ist 101 / Soll ~130 (excluding HTML comments)
- [ ] Status set to `passed`
