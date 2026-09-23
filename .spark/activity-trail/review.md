# Review Report: activity-trail

| | |
|---|---|
| **Phase** | Review |
| **Owner** | Reviewer (`/peer-review`) |
| **Input** | `git diff main...feat/activity-trail` (base `208a00c`, T1…T12), `.spark/activity-trail/plan.md` |
| **Status** | `changes-requested` |
| **Round** | 1 |
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
- **Verdict:** changes requested — one Must AC (AC-2.2, "same feature") is not met on the common path; everything else holds.
- **Open:** `none open` — F1 (Major), F2, F3 `fixed` by `/increment` fix-mode, awaiting re-review. F4, F5, F9–F12 `accepted` by the user (2026-09-23) as they stand.
- **Binding ruling:** §6 Verdict and the gate checklist below — the only binding location; there is no other round to point to
- **On conflict:** the numbered body below wins for everything except `Status`; log the mismatch as a finding at the next `/peer-review` and proceed — don't stop on it.

## 1. Scope

- **Reviewed:** all 30 files of `git diff main...feat/activity-trail` (13 commits): `src/aspark_guard/{activity,cli,config,trail}.py`, `hooks/hooks.json`, `bin/guard.py`, `.gitattributes`, README, `docs/evidence.md` §7–§8, all new/changed tests and the 9 payload fixtures. Surrounding code read: `cli.main`/`_root_for`, `ledger.append_to`/`read_jsonl`, `trail.feature_for_session`.
- **Run by me:** full suite under 3.13 → **206 tests OK** (before and after my fixes). Python 3.9: `py_compile` of every `src/` module and an import of `aspark_guard.cli` under `/usr/bin/python3` 3.9.6 (also with `-W error`) → OK. Real hook calls under 3.9 for all 9 subcommands → exit 0, empty stdout/stderr, correct lines, `.gitignore` created. A 3-writer × 300-line probe under 3.9 across repeated rotations (20 KB cap) → 0 lost-by-lock, 0 unparsable lines.
- **Not re-run:** `tests/bench_hooks.py` (machine loaded, as instructed). T1's live-harness facts are cited from evidence §7, not re-derived — none of conditions (a)–(d) applies except where F1/F3 lean on "resume fires a new SubagentStart" (cited, not doubted).
- **Tools:** no tool file, no aspark-graph, no constitution, no lenses. Scoped by the diff alone.
- **Open question (for PO/dev):** can the `Agent` tool be called without `subagent_type` (harness default `general-purpose`)? If so, `record_pending_task` (`activity.py:226-230`) parks `agent_type: null`, which never matches the start's type, so AC-5.1's label is lost. T1 does not say; not raised as a finding.

## 2. Plan Conformance

| Task | Implemented as planned? | Note |
|---|---|---|
| T1 | ✅ | Evidence §7 complete; D-T1-1…5 recorded; DoD gaps (screen latency, AskUserQuestion) accepted by the user. |
| T2 | ✅ | `record`, `activity` key, two handlers, manifest; `EXPECTED_EVENTS` edit per ruling Q1. |
| T3 | ✅ | Negative case + fail-open derive from `cli.EVENTS` via `support.ACTIVITY_COMMANDS`, so every new subcommand is covered. |
| T4 | ✅ | flock + 500 ms deadline, tail repair, rotation under lock, `O_EXCL` `.gitignore`; git-status test real. |
| T5 | ⚠️ | As amended by D-T1-1/-3: `permission-request` replaces `notification`; Notification unhooked (test pins it). |
| T6 | ⚠️ | Also skips starts with empty `agent_type` — beyond D-T1-4's wording (F10). |
| T7 | ⚠️ | Pairing, resume, rotation, null, no `stop_reason` all correct; but `feature` is re-inferred at stop (F1). D-T7-1 justified. |
| T8 | ✅ | D6 pending-file variant, exactly-one rule, 60 s window; D-T8-1 justified (no misleading status message). |
| T9 | ✅ | Markers in every content field incl. `permission_suggestions`, `reason`, transcript path; forced rotation; pending file checked. |
| T10 | ✅ | `scan` prints lines (current + rotated) and size; read-only asserted. |
| T11 | ⚠️ | README complete for AC-3.4/1.4/1.7/2.6/4.5/4.6; two inaccuracies fixed by me (F6, F8). |
| T12 | ⚠️ | Closed by user ruling on relative evidence; NFR-1 absolute bound unverified. Assessment below; F5, F7. |

**Ruling Q1 (user point 1) — confirmed.** Every removed line under `tests/` (`git diff … -- tests/ \| grep '^-'`) is: the old `EXPECTED_EVENTS` line and two `from support import GuardTestCase` import lines (extended to also import `ACTIVITY_COMMANDS`). No other existing assertion, fixture or test body changed; existing fixtures are untouched. `hook_commands()` now returns the `Agent` entry's command for `PreToolUse` (last entry wins) — identical string, so the existing shell test still runs the gate command.

**NFR-1 relative evidence (user point 2) — sound in direction, weaker in reproducibility; recorded, not waived or un-waived.** Sound: the new hooks run the same interpreter + `cli` import as the gate hooks, and the interleaved before/after (`pre-tool-use` 219→203, `post-tool-use` 210→216 ms median) shows the added `activity` import costs nothing measurable; `python3 -c pass` alone has p95 111 ms, so the bound is unreachable on this machine for any hook. Weak: (1) the load (7–105) makes noise larger than the ±10 ms the DoD asks to show, so "no regression" is proven only to ~±15 ms; (2) the decisive in-process figures (≤ 6 ms, 12/16/18 ms scan) have no recorded command although §8 says every number comes from the bench (F5); (3) max ≤ 500 ms was exceeded (626/682 ms) — also by existing hooks (566 ms), same attribution; (4) the absolute claim rests on §5's 47 ms from an M-series Mac measured before this feature. Expected on an unloaded M-series: ~50 ms + ≤ 16 ms — plausibly within bounds, still unmeasured.

**Deviations (user point 3).** D-T1-1 (PermissionRequest) and D-T1-2 (no `question`) are forced by §7's measurements and stay inside AC-1.3 ("e.g." reasons; 2 s met only via PermissionRequest). D-T1-3 uses the harness's own values; unknown → `other`, tested. D-T1-4 matches the trail's rule; extended to starts undocumented (F10). D-T1-5 verified above. D-T7-1 is justified, though the ±50 ms tests now compare against the start line's own `ts`, so they prove the arithmetic, not where `ts` is taken. D-T8-1 justified. All within the spec except that none of them covers F1.

## 3. Findings

| # | Severity | Location | Finding | Status |
|---|---|---|---|---|
| F1 | Major | `src/aspark_guard/activity.py:295` | `agent_run.feature` is re-inferred at stop instead of taken from the paired start. Reproduced under 3.9: start `feature: null` → subagent writes `spec.md` → run `feature: "feat-x"`. AC-2.2 (Must) requires the *same* feature; this is the usual first run of a feature (PO writes the first artifact), so a cockpit sees two different features for one run. Untested. **Fix:** let `_open_start` return the matched entry and write its `feature` when paired (inference only when unpaired), plus a test with a ledger write between start and stop — or the PO amends AC-2.2 to "inferred at stop" and the README says start and run may differ. | fixed |
| F2 | Minor | `src/aspark_guard/activity.py:208-215` | `task` is free text from the main model; a description such as "Review /Users/<name>/…" lands verbatim, breaking NFR-2's "no line contains the user's home path" and the README's "Paths aren't recorded at all" (`README.md:250`). **Fix:** in `sanitize_task` replace `str(Path.home())` (and the repo root) with `<outside-repo>` / relative; add a marker test with a home path in `description`. | fixed |
| F3 | Minor | `src/aspark_guard/activity.py:236-256` | A resume via `SendMessage` fires a new `SubagentStart` without a `PreToolUse(Agent)` (evidence §7). If a same-type launch is pending in the 60 s window, the resumed agent takes its label and the real launch gets `null` — a swap AC-5.4 forbids. **Fix:** skip `_claim_task` when this `agent_id` already has a `subagent_start` in the log (the scan `_open_start` already does). | fixed |
| F4 | Minor | `src/aspark_guard/activity.py:18`, `cli.py:19` | `import fcntl` runs at `cli` import, before `main`'s catch-all: where `fcntl` is missing, *every* hook (gates included) exits 1 with a traceback on stderr — fail-open and silence broken plugin-wide, not just for activity. README limits Windows already, so impact is bounded. **Fix:** `try: import fcntl` / `except ImportError: fcntl = None`; `_locked` yields False when None. | accepted |
| F5 | Minor | `docs/evidence.md:263-287` | §8 says every number comes from `bench_hooks.py`, but the in-process handler/scan figures and the `-X importtime` range — the core of the T12 relative argument — have no recorded command. **Fix:** record the snippet used, or add an in-process mode to `bench_hooks.py`. | accepted |
| F6 | Minor | `README.md:387-391`, `docs/evidence.md:296-297` | Cost statement counted `SubagentStop` as a new per-subagent hook start (3 instead of 2) and said the feature "adds hooks on 9 events". Corrected to 5 events + 1 matcher, 2 per subagent. | fixed |
| F7 | Minor | `tests/bench_hooks.py:72-73` | Comment claimed the bench agent's start is "buried" in the rotated file; the code plants none, so the cap row measures the no-match full scan. Comment corrected to what the code does (numbers unaffected). | fixed |
| F8 | Minor | `README.md:288-289` | "can't break or lose lines" overclaimed: a line that misses the 0.5 s lock deadline is dropped by design (D4). Qualifier added. | fixed |
| F9 | Nit | `src/aspark_guard/activity.py:107` | Each file can reach 2 MB − 1 + one line, so the pair can hold 4 MB + 2 lines, not AC-4.3's "4 MB plus one line"; `test_activity_rotation.py:80` hides this in 1 KB slack. **Fix:** rotate when `size + len(line) > MAX_BYTES`, or amend the wording. | accepted |
| F10 | Nit | `src/aspark_guard/activity.py:194-196` | Starts with empty `agent_type` are skipped too; D-T1-4 documents only stops. Consistent and harmless. **Fix:** extend D-T1-4's text. | accepted |
| F11 | Nit | `src/aspark_guard/activity.py:310-329` | Pairing reads without the lock; a rotation between reading `.1` and the current file can hide the start → `duration_ms: null` (safe direction). **Fix:** accept and note, or read under the lock. | accepted |
| F12 | Nit | `src/aspark_guard/activity.py:170-174` | A hook killed between the `O_EXCL` create and the write leaves an empty `.gitignore` that is never repaired, and activity files then show in `git status`. **Fix:** treat an empty file as absent (rewrite via tmp + `os.replace` only when size 0). | accepted |

## 4. Requirements Traceability

| Spec ID | Implemented at | Verdict |
|---|---|---|
| AC-1.1 / AC-1.2 | `cli.py` `handle_user_prompt_submit`/`handle_stop` → `activity.record_state` | ✅ met |
| AC-1.3 | `cli.py` `handle_permission_request` (D-T1-1); Notification unhooked | ✅ met (`question` not recorded, D-T1-2) |
| AC-1.4 / AC-1.7 | reader contract `README.md` "Reading it"; no synthetic lines anywhere | ✅ met |
| AC-1.5 | `cli.py` `handle_session_end`, `activity.end_reason` | ✅ met |
| AC-1.6 | every line carries its own `session_id`; `test_two_sessions_interleave…` | ✅ met |
| AC-2.1 | `activity.record_subagent_start` | ✅ met |
| AC-2.2 | `activity.record_agent_run` / `_open_start` | ⚠️ partial — duration correct, feature can differ (F1) |
| AC-2.3 / AC-2.4 / AC-2.5 / AC-2.6 | `_open_start` latest-unmatched; `null`; no `stop_reason` key; no synthetic finish | ✅ met |
| AC-2.7 | `trail.py` rename only; golden test `test_trail.py` | ✅ met |
| AC-3.1 / AC-3.2 | allowlists; `test_activity_privacy.py` | ⚠️ partial — free-text `task` may carry a path (F2) |
| AC-3.3 | `activity._ensure_gitignore`; git-status test | ✅ met |
| AC-3.4 | `README.md` activity section, `.gitattributes` | ✅ met |
| AC-4.1 / 4.2 / 4.4 / 4.5 | `_root_for`, empty stdout, `main` catch-all, `config.activity` | ✅ met (F4 outside POSIX) |
| AC-4.3 | `activity.append_locked` | ✅ met (bound wording, F9) |
| AC-4.6 / 4.7 / 4.8 | `FORMAT_VERSION`; `cli._scan`; manifest matchers test | ✅ met |
| AC-5.1…5.4 (Should) | `sanitize_task`, `record_pending_task`, `_claim_task` | ⚠️ partial — resume swap (F3), open question §1 |
| NFR-1 | evidence §8 | ⚠️ unverified absolute bound — accepted by the user at T12 |
| NFR-2 | `test_activity_privacy.py` | ⚠️ partial (F2) |
| NFR-4 | `test_activity_rotation.py` + my 3.9 probe | ✅ |
| NFR-6 / NFR-7 | only `EXPECTED_EVENTS` edited; stdlib only, no new subprocess; 1,980 lines = README | ✅ |

## 5. What Was Checked

- [x] Correctness: logic does what the acceptance criteria demand — except F1
- [x] Non-functional: NFR-2/4/6/7 hold (F2 aside); NFR-1 recorded as unverified
- [x] Error handling: failures are handled, not swallowed (fail-open by design; F4 outside POSIX)
- [x] Security: no injected input trusted, no secrets in code; no payload content logged (F2 aside)
- [x] Tests: exist, are meaningful, and pass (206 OK); timing tests use measured gaps, low flake risk
- [x] Readability: the next developer will understand this

## 6. Verdict

Changes requested. The write path is careful and correct: one lock for every append and rotation, tail repair, `O_EXCL` gitignore, allowlisted reasons, no content ever read. Fail-open and silence hold for every new subcommand, and `src/` runs on Python 3.9. Ruling Q1 is respected exactly. One Must criterion is not met: AC-2.2 asks for the run line to carry the *same* feature as its start, and the code re-infers it at stop. On a feature's first run the two differ (reproduced). That is F1, Major. It needs either a small code change or a PO amendment of AC-2.2. The user alone can waive it, and it has not been waived. F2 (a path inside a free-text label) is the other one worth doing before QA. The T12 relative evidence for NFR-1 holds up in direction. Its absolute bound stays unverified, as the user accepted at T12. I have neither waived nor reopened it. It needs the unloaded re-run and a recorded command for the in-process numbers (F5). I fixed F6–F8 myself (docs and one comment only) and re-ran the suite green.

---

## ✅ REVIEW GATE

*All boxes checked → `/demo-day` may start. Any box open → back to `/increment`. On
re-review, edit this same checklist in place — never duplicate it as a second gate.*

- [x] No open Blocker findings
- [ ] No open Major findings (or explicitly waived by the user, with reason recorded here) — F1 open
- [ ] Every Must AC traces to implementing code; no constitution non-negotiable violated — AC-2.2 partial (F1); no constitution
- [ ] All plan deviations documented and accepted — D-T1-1…5, D-T7-1, D-T8-1 and the T12 ruling are; the start-side skip of empty `agent_type` is not yet (F10)
- [x] Test suite runs green — 206 OK (3.13), after reviewer fixes
- [x] Line budget respected: Ist 119 / Soll ~150 (excluding HTML comments)
- [ ] Status set to `passed`
