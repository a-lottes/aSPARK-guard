# Constitution: aspark-guard

| | |
|---|---|
| **Scope** | Project-wide — binds every SPARK phase and every feature |
| **Owner** | The user (amended via `/charter`) |
| **Status** | `active` |
| **Date** | 2026-09-23 |

<!-- The constitution is the project's standing context. Every agent reads it before phase work.
     Keep it short and true; amend it with /charter when reality changes. -->

## 1. Product Principles

In priority order. These are the tie-breakers:

1. **Silence beats coverage.** A repo without `.spark/` must not notice the plugin exists: no file, no output, exit 0 (`tests/test_negative_case.py`).
2. **No false positive beats catching more.** A gate rule ships only after `guard.py check` over a real aSPARK project's history prints 0 blocks on features that ran cleanly, and that run is recorded in `docs/evidence.md` (CONTRIBUTING.md:21-35).
3. **Facts, not inferences.** The logs record what the harness delivered. They never contain a synthetic end, finish or `stop_reason`. The one inferred field (`feature`) is named as an inference in the README.
4. **Shipped means exercised.** README and `docs/evidence.md` claim only what has run. Every stated number (lines, tests, ms) has the command that produced it next to it (CONTRIBUTING.md:61-66).
5. **Primary user: the aSPARK author.** Every other guard user is affected but asks for nothing, so nothing may reach them unasked (spec `activity-trail` §2).

## 2. Project Profile & Active Lenses

- **Project type(s):** `cli`. The code is a Claude Code plugin whose only runtime surface is a terminal entrypoint. `bin/guard.py` dispatches one subcommand per hook event (`hooks/hooks.json`) plus `scan`/`check` for humans (`src/aspark_guard/cli.py:410-429`). There is no package export, no route handler or server, and no UI.
- **Characteristics:** none. No auth code. No network: there is no `urllib`/`socket`/`http` import in `src/`. No payments. No database: persistence is append-only JSONL under `.spark/.guard/`. Single locale. `handles-pii` was considered and deliberately not set; its privacy concerns are §4/§6 rules.
- **Active lenses:**

| Lens | Why it's active (or off) | Enforced in |
|---|---|---|
| `cli` | active — `bin/guard.py` is the whole interface. **Carve-out:** hook subcommands follow Claude Code's hook protocol. For them, always exiting 0 is fail-open, not a finding, and stdout carries only decision/context JSON. The lens binds `scan` and `check` in full. | `/story-time`, `/peer-review` |
| `security` | off — no triggering characteristic applies. Unprompted execution on other machines, content in logs and supply chain are covered by §3/§6. | — |
| `data` | off — no database; the JSONL logs are covered by §6 and the feature specs | — |
| `seo` / `ux` / `api` / `library` / `i18n` | off — no website, UI, API, published package or second locale | — |

- **Active-lens load:** 1 lens active.

## 3. Technical Constraints

- **Stack / runtime:** Python standard library only. No dependency, no build step, no lockfile (CONTRIBUTING.md:8-9; every import in `src/` is stdlib).
- **Interpreter floor:** code under `bin/` and `src/` runs on **Python 3.9**, because hooks run under the machine's `python3` (3.9.6 at `/usr/bin/python3` on the dev Mac; plan `activity-trail` D-T1-5). The test suite needs ≥ 3.10.
- **Platform:** POSIX only (macOS, Linux). The hook command is `python3 …`, and `activity.py` imports `fcntl` at module load (README.md:449-452).
- **Patterns to follow:** one entry point (`bin/guard.py` → `cli.main`), one handler per hook event, one module per concern (README.md:432-445). Every feature switch lives in `config.DEFAULTS`. Every gate rule ships with a `block`/`warn`/`off` mode (CONTRIBUTING.md:37-38).
- **Off-limits:**
  - Network and LLM calls.
  - Any subprocess other than `git rev-parse --short HEAD` and `git config user.name`, each with a 2 s timeout (`gitinfo.py:13-40`).
  - Hooks on ordinary tool calls. Matchers stay limited to `Write|Edit` and `Agent` (`hooks/hooks.json`; AC-4.8).
  - A gate rule that needs to know which ceremony is running (CONTRIBUTING.md:23-24).

## 4. Quality Bars (Definition of Done defaults)

- **Testing:** `python3 -m unittest discover -s tests -t tests` is green under Python ≥ 3.10 (210 tests, 2026-09-23). A change on a hook path adds tests in all three layers: behaviour fixture, hook contract, fail-open (CONTRIBUTING.md:46-54). Every newly hooked event gets a payload fixture in the shape a real harness run sent (`tests/fixtures/payloads/`, evidence §7).
- **Runtime check:** before `/peer-review` passes, every changed hook subcommand runs once through its manifest command line under a Python 3.9 `python3`, with exit 0 and empty stderr.
- **Accessibility:** N/A. There is no UI.
- **Performance:** there is no numeric latency bar. Every hook keeps the 5 s manifest timeout, and no feature adds a hook to ordinary tool calls. Any latency the README or evidence states comes from `tests/bench_hooks.py` (or a command recorded next to it), with machine and load named. A bar for the guard's own in-process share comes by amendment once the bench can measure it (review F5).
- **Privacy:** the marker test (`tests/test_activity_privacy.py`) finds 0 content leaks. No activity line contains an absolute or home path. Ledger and trail never store agent output (`last_assistant_message`).
- **Docs honesty:** the line and test counts in the README equal `wc -l src/aspark_guard/*.py` and the suite's count at the commit that changes them. `/peer-review` checks this.

## 5. Conventions

- **Naming / structure:** `tests/test_<module>.py`; one fixture file per artifact state in `tests/fixtures/artifacts/`; redacted, real-shape payloads in `tests/fixtures/payloads/`.
- **Branches:** one `feat/<feature>` branch per `.spark/<feature>/`, reviewed as `git diff main...feat/<feature>` (`review.md` `activity-trail`).
- **Evidence:** `docs/evidence.md` sections are dated records. New runs get a new section; old numbers are not rewritten.
- **Language:** all artifacts, code and reports are in English, whatever the chat language.

## 6. Non-Negotiables

The README invariants (README.md:376-406, CONTRIBUTING.md:6-19). They are blockers by definition:

1. **Degrade to silence.** No `.spark/` means no output, no files, exit 0.
2. **Fail open (on POSIX).** On any error, exception or hostile input, the action proceeds with exit 0 and no output. This holds on POSIX only: where `fcntl` is missing, every hook currently fails (review F4, accepted). Fail-open on every platform is a future feature via `/story-time`.
3. **Never block silently.** Every denial names the rule, the state that triggered it, and every way forward.
4. **State and form only, never quality.** Judgment belongs to aSPARK's agents.
5. **No network, no LLM, no dependency.** Plugin hooks bypass the workspace-trust prompt, so the code stays auditable by the people it runs for.
6. **Nothing is written outside `.spark/`.** Not `.gitattributes`, not a marker file. Suggest it in the README instead.
7. **No override the agent can grant itself.** Agent writes to `overrides.jsonl` are denied (`overrides-are-human-only`).
8. **No content in any log.** Prompts, tool input/output, agent messages and thinking are never written.

## 8. QA Method

<!-- Confirmed by the user, 2026-09-23. Changes the QA phase's method only, never its coverage:
     qa.md is still produced, and every AC and QA-owned NFR is verified under its own ID. Only
     /charter may amend this section. -->

- **Browser-observable surface:** `no`. The repo has no HTML, JS or route handlers. Its only surfaces are hook subprocesses started by Claude Code (`hooks/hooks.json`) and the terminal output of `bin/guard.py scan|check`. The one UI consumer (Mission Control) lives in `aspark-vscode` and is out of scope (spec `activity-trail` §6).
- **Substitute verification method:** a live Claude Code session driven by the user, with the plugin loaded from the working tree. Each AC gets one performed step, and its evidence is read from the guard's own files. Procedure:
  1. **Setup.** Create a throwaway git repo outside every real project, with one commit and a `.spark/` directory (plus feature artifacts where an AC needs them). Record `claude --version`, `command -v python3 && python3 --version`, and `git -C /Users/andreaslottes/aSPARK-guard rev-parse --short HEAD`.
  2. **One copy only.** Run `claude plugin disable aspark-guard@aspark` before the run and `claude plugin enable aspark-guard@aspark` after it. Otherwise every event is logged twice.
  3. **Perform.** The QA Tester writes one numbered step per AC. The user runs `claude --plugin-dir /Users/andreaslottes/aSPARK-guard` in the throwaway repo and performs the steps, noting the wall-clock time wherever an AC has a time bound. Steps that need no human (prompt → stop, subagent launches, a resume) may be run by the tester headless with `claude -p --plugin-dir …`. Permission dialogs, `/clear` and `/exit` need the interactive user (evidence §7).
  4. **Inspect.** Read `.spark/.guard/activity.jsonl` (plus `.1` and `activity.pending.jsonl`), `ledger.jsonl` and `trail.jsonl`. Run `python3 /Users/andreaslottes/aSPARK-guard/bin/guard.py scan .` and `… check .`, and `git status --porcelain`. Quote the observed lines in `qa.md` under each `AC-`/`NFR-` ID.
  5. **Not live-producible** (2 MB rotation, killed session, unwritable `.guard/`, malformed payload, lock contention): pipe a payload into the manifest's own command line from a shell. Label the row "hook-level, not live".
  6. **Negative case.** Repeat one prompt and one subagent run in a repo without `.spark/`. Pass means `git status --porcelain` is empty and no output appears.
  7. Anything the tester could not observe is recorded as not verified. It is never derived from reading source.

## 9. Project Context

- **Shape:** `brownfield`.

**Product brief:**

- **Primary user:** `confirmed by user` — the aSPARK author; every other guard user is affected without asking for anything (`.spark/activity-trail/spec.md:37-42`).
- **Problem today:** `inferred from README.md:6-12` — aSPARK Core's gates are prompts, so an agent can reason its way past one.
- **Smallest version:** `inferred from README.md:14-20` — deny a gate-violating write before it happens; record every override as a dated, hash-bound line.
- **Success signal:** `inferred from README.md:44-48` — a full feature loop on someone else's project with rules firing where they should and staying quiet where they shouldn't. Not yet achieved.
- **Stack:** `inferred from CONTRIBUTING.md:8-10, hooks/hooks.json` — Python stdlib, command hooks, `python3` on `PATH`.
- **Non-negotiables:** see §6.

**System picture:**

- **Stack & entry points:** `inferred from bin/guard.py:1-23, hooks/hooks.json` — 9 hook events, 10 entries, one `guard.py <subcommand>` each; `scan`/`check` for humans.
- **Module structure:** `inferred from README.md:432-445` — `cli`, `artifacts`, `ledger`, `drift`, `overrides`, `rules`, `templates`, `trail`, `activity`, `config`, `gitinfo`; 2,006 lines total.
- **Data model:** `inferred from README.md:221-297` — append-only committed `ledger.jsonl` and `trail.jsonl`; local, rotated, git-ignored `activity.jsonl`; `overrides.jsonl` per feature; optional `.spark/guard.json`.
- **Test practice:** `inferred from CONTRIBUTING.md:40-59` — `unittest`, three layers, `tests/bench_hooks.py` for cost.
- **How to run:** `inferred from README.md:207-214, 412-414` — `python3 bin/guard.py scan|check <path>`; the suite as in §4.
- **Known pain points:** `inferred from README.md:449-469, docs/evidence.md §6/§8` — ~50–200 ms of interpreter start on every `Write`/`Edit` everywhere; no Windows; concurrent ledger writes untested; no foreign-project loop yet.
  - The README contradicts the code in five places, left for a docs feature:
    - "Python 3.11+" (`:331`)
    - "~47 ms" presented as the general cost (`:386-389`)
    - `git rev-parse` named as the only subprocess (`:406`; `git config user.name` also runs)
    - "142 tests" (`:40`)
    - the negative case as "the first test" (`:382`)

---

## Amendments

| Date | Change | Why |
|---|---|---|
| 2026-09-23 | Initial constitution. Profile `cli` with the hook-protocol carve-out; security and data lenses off; Python 3.9 runtime floor (tests ≥ 3.10); no numeric latency bar; fail-open limited to POSIX; §8 QA Method declared (live `--plugin-dir` session, marketplace copy disabled for the run). All decisions confirmed by the user. | `/demo-day` for `activity-trail` needs a declared §8 QA Method; until now the README invariants were the only binding rules |
