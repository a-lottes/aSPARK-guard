# Review Report: activity-trail

| | |
|---|---|
| **Phase** | Review |
| **Owner** | Reviewer (`/peer-review`) |
| **Input** | `git diff main...feat/activity-trail` (base `208a00c`); round 3: `git diff 03fe1f5..HEAD` (T13–T17, `d653462`); `.spark/activity-trail/plan.md`, amended spec (C14–C16), `.spark/constitution.md` |
| **Status** | `passed` |
| **Round** | 3 |
| **Date** | 2026-09-23 |

<!-- Handoff: read this block first, the numbered sections below by exception. Whoever
     writes to this report — including `/increment` in fix-mode, which is not this
     report's owner — updates it in the same edit that closes or re-rules a finding:
     overwrite in place, never append. The block holds one current state, never a
     per-round log; a stale block is a defect, not a cosmetic issue.

     Re-review: bump `Round` yourself (only the owner bumps it, never `/increment`) at
     the start of the pass, then overwrite every section below in place — §1 Scope, §2
     Plan Conformance, §3 Findings, §4 Traceability, §6 Verdict and the gate checklist
     all hold exactly one current state, never a `## Round N` heading or a second gate.
     History lives in git, not in this file. -->

**Handoff**
- **Status:** mirrors the header table above (authoritative for `Status`).
- **Verdict:** review gate met in round 3 — T13–T16 verified against the amended spec and the constitution, no Blocker or Major open; `passed` awaits the user's close.
- **Open:** `none` — Blockers: none; Majors: none. F17 `fixed r3` (revert-checked); F16 `accepted` by the user (2026-09-23) as a later `/story-time` follow-up; F4, F9–F13 `accepted`. Gate closed `passed` by the user after round 3, 2026-09-23. Next: `/demo-day` re-test.
- **Binding ruling:** §6 Verdict and the gate checklist below — the only binding location; there is no other round to point to
- **On conflict:** the numbered body below wins for everything except `Status`; log the mismatch as a finding at the next `/peer-review` and proceed — don't stop on it.

## 1. Scope

- **Reviewed:**
  - r1: the full feature diff, T1…T12.
  - r2: fix commit `4f5b665`.
  - **r3:** `git diff 03fe1f5..HEAD` in full. That covers `activity.py` (T13, T15), `cli.py` `_scan` (T16), the new tests and the `subagent_stop_double.json` fixture, `bench_hooks.py` (`inproc`/`compare`), evidence §9, the README, and the spec/plan amendments.
  - Also read for r3: the new constitution, and QA `qa.md` B1/B2/B4.
- **Standard (r3):** the constitution is now active and binding.
  - Its §4 quality bars (three test layers, 3.9 runtime check, docs honesty) and §6 non-negotiables were checked against the diff.
  - The `cli` lens (hook carve-out) was checked against `scan`'s changed output.
  - NFR-1 is judged as amended (C15): no numeric bar, measured and labelled.
- **Run by me, r3:**
  - Suite under 3.13 → **223 tests OK** (after the F17 test).
  - Under `/usr/bin/python3` 3.9.6 with `PATH=/usr/bin:/bin`, through the `hooks.json` command lines: untyped `Agent` launch → `SubagentStart` → two `SubagentStop`. Each exits 0 with empty stdout and stderr. The start gets `task: "untyped"`; both runs are measured from the same start (335, 675 ms).
  - `scan` under 3.9 with `{"activity": false}` → `activity=False`, exit 0, empty stderr.
  - `wc -l src/aspark_guard/*.py` → 2,016, matching the README.
- **Re-derived, not cited:** B4, B1 and B2 are fixes to facts, so condition (a) applies. Each new test fails on the r2 code:
  - T13's second stop returned `null` there.
  - T15's parked type was `null` there.
  - T16's `enabled:` line had no `activity=`.
- **Cited, not re-derived:**
  - "An untyped launch starts as `general-purpose`": `qa.md` B1.
  - The in-process cost figures: evidence §9. The bench was not re-run; I read `run_inproc` and its seeding.
- **Tools:** no tool file, no aspark-graph.

## 2. Plan Conformance

| Task | Implemented as planned? | Note |
|---|---|---|
| T1–T12 | ✅ / ⚠️ as in r1–r2 | Deviations D-T1-1…5, D-T7-1, D-T8-1 and the T12 ruling were judged justified and in-spec in r1. The start-side skip (F10) is accepted by the user. |
| T13 | ✅ | `_scan_agent` no longer resets on `agent_run` (`activity.py:332-365`). The fixture has the real key set. Tests live in `TestDoubleStop` rather than `TestAgentRun` (naming only). |
| T14 | ✅ | `README.md:289-297` states the AC-2.8 rule as the spec words it, the brief false "finished", one trail line per finish, and `v` stays 1. |
| T15 | ✅ | `DEFAULT_SUBAGENT_TYPE` (`activity.py:48,251`). Tests live in `TestUntypedLaunch` rather than `TestTaskLabel` (naming only). Closes r2's open question. |
| T16 | ✅ | `cli.py:343-344`, effective value from `Config.activity`. The test covers default, `activity:false` and `enabled:false`, with the tree unchanged. |
| T17 | ✅ | The `inproc` and `compare` modes exist and match evidence §9's commands. §8 is not rewritten (constitution §5). Counts match. README cost figure corrected (F15). |

**Ruling Q1 still holds.** Round 3 edits no existing assertion; the only new assertions are in new test methods.

**NFR-1, as amended (C15).** Every guard number now has its command next to it: `inproc` for the guard's own share, and `compare` for the gate hooks against `main`, run alternately. The machine and its load are named. The gate hooks show a median difference of ≤ 4 ms, which is no measurable regression. The worst single hook invocation was 682 ms, far below the 5 s timeout. The r1 caveat that the absolute bound was unverified falls away with the numbers themselves. F5 is resolved by T17.

## 3. Findings

| # | Severity | Location | Finding | Status |
|---|---|---|---|---|
| F1 | Major | `src/aspark_guard/activity.py:311` | `agent_run.feature` was re-inferred at stop instead of taken from the paired start (AC-2.2). | fixed r2 |
| F2 | Minor | `src/aspark_guard/activity.py:217-231` | The free-text `task` could carry a home or absolute path (NFR-2). | fixed r2 |
| F3 | Minor | `src/aspark_guard/activity.py:204` | A resumed agent could take a waiting launch's label (AC-5.4). Still holds after T13 (`test_a_resume_after_a_double_stop_takes_no_waiting_label`). | fixed r2 |
| F4 | Minor | `src/aspark_guard/activity.py:18`, `cli.py:19` | `import fcntl` at load time: without `fcntl`, every hook exits 1 with a traceback. Now recorded in constitution §6.2 as POSIX-only fail-open. | accepted |
| F5 | Minor | `docs/evidence.md` §8 | The in-process figures had no recorded command. T17 adds `bench_hooks.py inproc` and records it in §9. | fixed r3 |
| F6 | Minor | `README.md` cost section, `docs/evidence.md` §8 | The per-subagent hook count was wrong (3 → 2). | fixed r1 |
| F7 | Minor | `tests/bench_hooks.py` `make_project` | A comment claimed a start the code didn't plant. | fixed r1 |
| F8 | Minor | `README.md` "Bounded and local" | "Can't lose lines" ignored the 0.5 s lock drop. | fixed r1 |
| F9 | Nit | `src/aspark_guard/activity.py:107` | The pair of files can hold 4 MB + 2 lines, not "+ 1 line". | accepted |
| F10 | Nit | `src/aspark_guard/activity.py:196-198` | The empty-`agent_type` skip also applies to starts, but D-T1-4 names only stops. | accepted |
| F11 | Nit | `src/aspark_guard/activity.py:332-365` | The pairing read runs without the lock; a rotation race can give `null` (the safe direction). T13 doesn't change this. | accepted |
| F12 | Nit | `src/aspark_guard/activity.py:170-174` | A hook killed mid-create leaves an empty `.gitignore` that is never repaired. | accepted |
| F13 | Nit | `src/aspark_guard/activity.py:217` | A path after a single-slash `scheme:`, or a Windows path, is not masked. The current user's home is still caught. | accepted |
| F14 | Minor | `README.md` counts | Line and test counts went stale after r2. | fixed r2 |
| F15 | Minor | `README.md:408-410` | The r3 cost sentence said "about 1 ms median (≤ 7 ms p95)" with `.spark/`, but evidence §9 shows `subagent-stop` at 2.3 ms median and 8.1 ms p95. Constitution §4 (docs honesty) and principle 4 require stated numbers to match their source. Corrected to "1–2 ms median (≤ 8.1 ms p95)" and "≤ 12.5 ms p95 (16.1 ms max)" at the cap. | fixed r3 |
| F16 | Minor | `src/aspark_guard/cli.py:320-322` (`_scan`), `bin/guard.py` | The `cli` lens binds `scan` in full. The line T16 changed conforms: results go to stdout, there is no colour or prompt, and exit is 0. Three pre-existing gaps are not from this diff: `guard.py scan --help` treats `--help` as a path and silently scans the cwd's root; there is no `--version`; and there is no machine-readable mode, although `scan` is NFR-5's only observability surface and T16 just changed its format. **Fix:** route to a `/story-time` follow-up for `scan`/`check` ergonomics (at least `--help`, and treating an unknown flag as an error on stderr). Not this feature's scope. | accepted |
| F17 | Minor | `tests/test_install.py` (`TestInstalledCopyRuns`) | Constitution §4 says a change on a hook path adds tests in all three layers. T13 and T15 add behaviour tests only, and the existing fail-open tests cover hostile input. No hook-contract test drives the double stop or the untyped launch through the manifest command line; that ran once by hand (evidence §9, and my r3 run). Fixed by `test_an_untyped_launch_and_a_double_stop_through_the_real_command_lines`. Revert-checked in a worktree: fails with r2's `activity.py` (`None != 'untyped'`, B1) and with only the `agent_run` reset restored (B4). | fixed r3 |

## 4. Requirements Traceability

| Spec ID | Implemented at | Verdict |
|---|---|---|
| AC-1.1 … AC-1.7 | `cli.py` state handlers → `activity.record_state`; README "Reading it" | ✅ met |
| AC-2.1 | `activity.record_subagent_start` | ✅ met |
| AC-2.2 (amended) | `record_agent_run` + `_scan_agent` latest start, no reset (`activity.py:311,332-365`); `TestDoubleStop` | ✅ met r3 |
| AC-2.3 (amended) | latest `subagent_start` wins; `test_a_resume_after_a_double_stop_measures_from_its_own_start` | ✅ met r3 |
| AC-2.4 (amended) | no start → `null` for every finish; `test_two_finishes_without_a_start_both_have_no_duration` | ✅ met r3 |
| AC-2.5 / AC-2.6 | no `stop_reason` key; no synthetic finish | ✅ met |
| AC-2.7 (amended) | trail unchanged, one line per finish; `test_the_trail_gets_one_line_per_finish` | ✅ met r3 |
| AC-2.8 (new) | `README.md:289-297` reader contract; lines never rewritten (`test_the_first_line_is_left_as_it_was`) | ✅ met r3 |
| AC-3.1 … AC-3.4 | allowlists, `sanitize_task`, `.gitignore`, README | ✅ met (F13 accepted) |
| AC-4.1 … AC-4.8 | `_root_for`, `main` catch-all, rotation, `config.activity`, `v`, `_scan` (+ `activity=`, `cli.py:343-344`), matchers | ✅ met (F4, F9 accepted) |
| AC-5.1…5.4 (Should) | `sanitize_task`, `record_pending_task` default type (`activity.py:251`), `_claim_task`, resume skip | ✅ met r3 |
| NFR-1 (amended) | evidence §9 `inproc`/`compare`; README cost section | ✅ r3 |
| NFR-2 | `test_activity_privacy.py`, `test_paths_in_the_label_are_masked` | ✅ |
| NFR-4 | `test_activity_rotation.py` | ✅ |
| NFR-5 | `scan` counts + effective switch | ✅ r3 |
| NFR-6 | only `EXPECTED_EVENTS` edited; `subagent_stop_double.json` added (A8) | ✅ |
| NFR-7 | stdlib only; 2,016 lines = README | ✅ |

## 5. What Was Checked

- [x] Correctness: logic does what the (amended) acceptance criteria demand
- [x] Non-functional: NFR-1 as amended, and NFR-2/4/5/6/7, hold. Constitution §6 non-negotiables are unaffected by r3.
- [x] Error handling: failures are handled, not swallowed (fail-open on POSIX, constitution §6.2)
- [x] Security: no injected input trusted, no secrets; no payload content logged
- [x] Tests: exist, are meaningful, and pass (223 OK); every new test fails on the r2 code, the F17 manifest test included.
- [x] Readability: the next developer will understand this

## 6. Verdict

The gate is met in round 3. B4 is fixed as the amended spec asks ("last stop wins"). Every finish now pairs with the agent's latest start. A double stop gives two measured lines with no `null`. Lines already written stay unchanged, and the trail keeps one line per finish. A resume that brings its own start measures only itself, and F3's label protection still holds after a double stop. I confirmed all of this in tests that fail on the r2 code, and once through the manifest under Python 3.9. B1 (the untyped launch's label) and B2 (`scan` showing the effective switch) are fixed and tested. NFR-1, as amended, is now measured and labelled with its commands, so F5 is closed. I found no violation of the constitution's non-negotiables. I corrected one misstated cost figure in the README (F15). F16, three pre-existing `cli`-lens gaps on `scan`, is accepted by the user as a later follow-up. F17, the missing manifest-level test, is fixed and revert-checked. No Blocker or Major is open. The user's earlier `passed` does not carry over a changed diff, so Status is `in-review` until the user closes the gate.

---

## ✅ REVIEW GATE

*All boxes checked → `/demo-day` may start. Any box open → back to `/increment`. On
re-review, edit this same checklist in place — never duplicate it as a second gate.*

- [x] No open Blocker findings
- [x] No open Major findings (or explicitly waived by the user, with reason recorded here) — none open; B4's fix verified
- [x] Every Must AC traces to implementing code; no constitution non-negotiable violated — incl. amended AC-2.2/2.3/2.4/2.7 and new AC-2.8
- [x] All plan deviations documented and accepted — D-T1-1…5, D-T7-1, D-T8-1, the T12 ruling, F10; T13–T17 as planned (test class names only)
- [x] Test suite runs green — 223 OK (3.13); manifest commands under 3.9.6 exit 0 with empty stderr
- [x] Line budget respected: Ist 130 / Soll ~150 (excluding HTML comments)
- [x] Status set to `passed` — by the user after round 3, 2026-09-23
