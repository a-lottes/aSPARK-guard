# Release: activity-trail

| | |
|---|---|
| **Phase** | Keep |
| **Owner** | Release Manager (`/go-live`) |
| **Input** | `review.md` (`passed`, round 3), `qa.md` (`passed`, round 2) |
| **Status** | `preparing` |
| **Version** | v0.2.0 |
| **Date** | 2026-09-23 |

<!-- Handoff: read this block first, the numbered sections below by exception. Whoever
     writes to this report updates it in the same edit that changes status or actions:
     overwrite in place, never append. The block holds one current state, never a
     per-round log; a stale block is a defect, not a cosmetic issue. -->

**Handoff**
- **Status:** mirrors the header table above (authoritative for `Status` and `Version`).
- **Summary:** v0.2.0 adds the local, metadata-only activity log (session state, subagent runs with duration and label). Pre-flight is green; the release commit and local tag `v0.2.0` are prepared on `feat/activity-trail`. Nothing has been pushed.
- **Open:** `1 outstanding`: the user's go for fast-forwarding `main` and pushing `main` plus `v0.2.0`. Pushing `main` publishes to every marketplace user. Then the smoke check (§3).
- **Binding ruling:** §3 Release Actions and the KEEP GATE below carry the final ruling.
- **On conflict:** the numbered body below wins for everything except `Status`/`Version`; log the mismatch as a finding at the next `/go-live` and proceed. Don't stop on it.

<!-- Budget: ~100 lines. -->

## 1. Pre-Flight Checks

<!-- Verified immediately before releasing — not copied from earlier reports. Run 2026-09-23 on 9641cf3, re-run on the release commit. -->

- [x] `review.md` status is `passed` (round 3; REVIEW GATE fully checked, Open `none`)
- [x] `qa.md` status is `passed` (round 2; QA GATE fully checked, Open `none`), verified by the project's declared QA method: a live Claude Code session, per constitution §8. This is a standing project fact, not an override.
- [x] Full test suite green: 223 tests OK (`python3.13 -m unittest discover -s tests -t tests`), in the working tree, in a fresh clone and on the release commit
- [x] Build succeeds from a clean checkout: no build step (stdlib only, §3). A fresh `git clone` at `9641cf3` is green, and its modules import under `/usr/bin/python3` 3.9.6
- [x] Constitution §4 runtime check: all 10 hook subcommands (11 manifest calls, including a double stop) run through the `hooks.json` command line with `PATH=/usr/bin:/bin` (3.9.6). Exit 0 with empty stdout and stderr, both in a `.spark/` repo and in a repo without one. The repo without `.spark/` got no file (`git status --porcelain` empty)
- [x] `guard.py scan .` exit 0: 0 drift, `activity=True`. `guard.py check .`: 0 would be blocked. `check` on `aspark-vscode`: 0 of 1 would be blocked
- [x] README counts equal reality: 223 tests, `wc -l src/aspark_guard/*.py` = 2,016
- [x] No uncommitted changes in the working tree before the release edits

## 2. Changelog

<!-- Mirrors CHANGELOG.md § 0.2.0 (new file, repo root). -->

### Added
- A live activity log in aSPARK projects: for every Claude session, whether it is working, done with its turn, waiting for you at a permission prompt, or closed. A dashboard can show it from your project alone.
- Every subagent's start and finish, with how long it ran, its likely feature, and a short label of what it was asked to do (paths masked).
- `guard.py scan` reports whether the activity log is on, its line count and its size.
- An `"activity"` switch in `.spark/guard.json` to turn the log off (on by default).

### Changed
- The guard also runs briefly on each prompt, turn end, permission prompt, session end and subagent launch or start. It never blocks and does nothing without `.spark/`. The cost is measured in `docs/evidence.md` §9.
- The new log stays on your machine: it is kept out of git, holds metadata only (never prompts, tool output or messages), and is capped at 2 MB plus one older file.

### Fixed
- Nothing. The ledger, the trail and every gate rule behave as in 0.1.0.

## 3. Release Actions

| Action | Result |
|---|---|
| Version bump & tag | 0.1.0 → 0.2.0 in `.claude-plugin/plugin.json` and the README status line; `CHANGELOG.md` added. Release commit on `feat/activity-trail`, plus a local annotated tag `v0.2.0` on it. **Not pushed.** Minor bump: new hooks, a new log file and a config key, all additive. Ledger, trail, config and the rules are unchanged, so nothing breaks |
| PR / merge | **Pending go.** Direct mode: `git checkout main && git merge --ff-only feat/activity-trail` (linear history, `origin/main` = merge base `208a00c`) |
| Deploy | **Pending go.** `git push origin main v0.2.0`. The aSPARK marketplace sources `a-lottes/aSPARK-guard` with no pinned ref, so this push is the publish |
| Post-release smoke check | **Pending.** `claude plugin marketplace update aspark`, then `claude plugin update aspark-guard@aspark`, then `claude plugin list` shows 0.2.0. One prompt in a throwaway `.spark/` repo writes `session_state` lines; `scan` shows `activity=True`; a repo without `.spark/` stays empty |
| Rollback path | **Before the push:** `git tag -d v0.2.0 && git reset --hard 9641cf3` on the branch; `main` is untouched. **After the push:** on `main`, run `git restore --source=208a00c -- bin src hooks tests README.md docs`. Set `plugin.json` to 0.2.1 and add a `CHANGELOG.md` line "0.2.1 restores 0.1.0 behaviour". Commit, then `git push origin main`. Users get the 0.1.0 code under 0.2.1, and `.spark/` artifacts stay. Never force-push `main` or delete a pushed tag. **Per project, no release needed:** `.spark/guard.json` `{"activity": false}` |

## 4. Learnings (Keep!)

- **What went well:** the live session under §8 found B4 (a second finish for one run), which 200+ unit tests could not see. The fix was tested with the real payload shape (`subagent_stop_double.json`). Fail-open and silence held in every pre-flight call.
- **What we'd do differently:** declare §8 and the 3.9 runtime floor at `/charter` *before* the first `/demo-day`, not mid-cycle. Also give the bench an in-process mode from the start: T12 had to close on relative evidence by user ruling.
- **Patterns worth reusing:** (CLAUDE.md candidates) run hooks through the manifest command line with `PATH=/usr/bin:/bin` to prove the 3.9 floor. Keep a payload fixture for every harness quirk you see live. Pushing `main` of an unpinned marketplace source is a publish, so treat it as one. Edit `.spark/` files only through Write/Edit, never with sed: the ledger won't see the change, and `scan` will report drift.
- **Follow-ups (owner: user, via `/story-time`):** F16 (`scan --help`, `--version`), B3 (non-string `session_id`), and the five README-versus-code contradictions (constitution §9).

---

## ✅ KEEP GATE

- [x] All pre-flight checks passed at release time
- [x] Changelog written in user-facing language
- [ ] Release actions executed and verified (or `aborted` with reason): push, merge and smoke check await the user's go
- [x] Learnings recorded
- [x] Line budget respected: Ist 75 / Soll ~100 (excluding HTML comments)
- [ ] Status set to `released`: `preparing` until the go and the smoke check
