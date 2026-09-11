# aspark-guard

> **Deterministic gate enforcement and a hash ledger for [aSPARK](https://github.com/a-lottes/aSPARK).**
> Silent in every project that doesn't use aSPARK.

aSPARK Core is Markdown prompt material with no runtime, which makes its quality
gates **requests to a language model**: *"read `qa.md`, and if there are open
blockers, refuse the release."* aSPARK's own roadmap names the consequence:

> *"The gates are prompt-enforced, not code-enforced. They hold until an agent under
> context pressure reasons its way around one — and a good-sounding reason is, from
> the agent's own view, a passed gate."*

`aspark-guard` is a companion plugin that adds what a prompt cannot provide: a check
that runs **outside** the model, on the tool call itself. Two guarantees when it is
complete:

1. **No gate can be skipped silently.** A write that violates a phase precondition is
   denied before it happens, however good the reasoning behind it sounded.
2. **No override stays invisible.** Gates can be overruled — but only through a dated,
   hash-bound entry in the repo, reviewable in the pull request.

Core is not modified. Nothing here runs unless a project has a `.spark/` directory.

---

## Status

**This is `0.0.1`. Two of six milestones are built.**

| Milestone | What it does | State |
|---|---|---|
| **M0** Skeleton | Plugin manifest, four wired hooks, payload parsing, the silence and fail-open invariants | **Built** |
| **M1** Ledger + drift check | Every `.spark/` write recorded with its SHA-256 and status; artifacts edited outside the loop reported at session start | **Built** |
| **M2** Gate guard | Rules R1–R3 deny writes that violate a phase precondition | Not built — `pre-tool-use` allows everything |
| **M3** Override mechanics | R4 plus hash-bound override entries | Not built |
| **M4** Template validator + trail | Form drift warnings; agent-run trail | Not built — `subagent-stop` is inert |
| **M5** Release | README, marketplace entry, `0.1.0` | Not built |

So today the plugin **observes and reports; it does not yet block anything.** That is
worth having on its own — the ledger is what makes "`spec.md` was approved when
`plan.md` was written" checkable instead of merely plausible — but it is not yet the
enforcement layer the intro describes.

---

## What it records

### `.spark/.guard/ledger.jsonl` — append-only, commit it

One line per write under `.spark/`:

```json
{"ts":"2026-09-11T09:41:22Z","event":"artifact_write","feature":"weekly-stats",
 "path":".spark/weekly-stats/spec.md","sha256":"9f2c…","status":"approved",
 "git_head":"a1b2c3d","session_id":"abc123","agent_type":"product-owner"}
```

No entry stores a "before" hash — the previous line for that file *is* the before.
The chain is the record.

**Why this isn't redundant with git:** git only sees what gets committed, and collapses
every intermediate state of a commit into a single diff. The ledger dates each status
change on its own.

Three things are deliberately *not* recorded: writes outside `.spark/`, the guard's own
files, and a write that leaves the content byte-identical to the last entry (a no-op
edit, or a write the tool ultimately failed to make).

### Drift detection at session start

If an artifact's current content differs from its last ledger entry, it was edited
outside the loop — in an editor, by a script, by anything that doesn't pass through a
hook. One line of context says so at the next session start:

```
aspark-guard: 1 .spark artifact changed outside the loop since the last recorded write:
  - .spark/weekly-stats/spec.md
Their current content is not what the ledger recorded, so any status they carry is
unverified. Re-read them before relying on a gate.
```

It **detects** the gap; it cannot prevent one. Only a substrate that refuses to treat
the filesystem as authoritative could, and that is the architecture aSPARK deliberately
does not have.

Files the ledger has never seen are not drift — they predate the install, which is the
normal case on adoption and stays quiet.

---

## Install

```bash
claude plugin marketplace add a-lottes/aSPARK-guard
claude plugin install aspark-guard@aspark-guard
```

Then restart Claude Code. Requires Python 3.11+ on `PATH` as `python3`. POSIX only for
now (macOS, Linux) — see *Known limits*.

Check that it sees your project:

```bash
python3 /path/to/aSPARK-guard/bin/guard.py scan .
```

**Recommended, one line, once per project** — the logs are append-only, so a conflict
between two branches is never a conflicting edit, only a conflicting file:

```bash
echo '.spark/.guard/*.jsonl merge=union' >> .gitattributes
```

The guard will not write this for you. It never touches anything outside `.spark/`.

---

## Configuration

Optional, at `.spark/guard.json`. Absent or malformed means these defaults:

```jsonc
{
  "enabled": true,
  "ledger": true,          // record writes            (M1)
  "drift_check": true,     // report outside edits     (M1)
  "trail": true,           // agent-run trail          (M4, inert)
  "template_check": true,  // template contract        (M4, inert)
  "rules": {               // "block" | "warn" | "off" (M2/M3, inert)
    "plan-requires-approved-spec":  "block",
    "qa-requires-passed-review":    "block",
    "release-requires-green-gates": "block",
    "overrides-are-human-only":     "block"
  }
}
```

---

## Invariants

Non-negotiable, and tested:

1. **Degrade to silence.** No `.spark/` directory → no output, no files, nothing. A
   repo that doesn't use aSPARK must not notice this plugin exists. This is aSPARK
   Core's own rule for optional integrations, and it is the first test in the suite.
2. **Fail open, always.** Malformed payload, missing file, corrupt config, unwritable
   directory, unexpected exception → the action proceeds. A guard that blocks when it
   is unsure trains people to switch it off, and then it guards nothing.
3. **Never slow.** 5 s timeout in the manifest; it reads at most a handful of small
   files. Measured at **~47 ms per invocation** on an M-series Mac — of which roughly
   40 ms is the Python interpreter starting up, not the guard working. That cost is
   paid on every `Write`/`Edit` in every project, including ones with no `.spark/`
   directory, and it is the honest price of the current design.
4. **Never block silently.** Once M2 lands, every denial names the rule, the state that
   triggered it, and both legitimate ways forward.
5. **State and form only, never quality.** Anything requiring judgment belongs to the
   agents.
6. **No network, no LLM, no dependency.**

Point 6 is not aesthetics. Plugin hooks **bypass the workspace-trust prompt**, so this
code runs on other people's machines unasked. It stays standard-library-only, under a
thousand lines, and readable in one sitting so that it can be audited by the people it
runs for. The only subprocess it ever spawns is `git rev-parse --short HEAD`.

---

## Development

```bash
python3 -m unittest discover -s tests -t tests
```

48 tests, no dependencies, no network, no Claude Code required. Three layers:

- **Behaviour against fixtures** — one artifact state per fixture: draft, approved,
  uninstantiated template, broken header table.
- **Hook contract tests** (`tests/fixtures/payloads/`) — recorded payloads in the shape
  Claude Code documents, so an API change surfaces here rather than as a plugin that
  silently stopped working.
- **Fail-open tests** — every hostile input we could think of must yield exit 0 and no
  output.

```
bin/guard.py              one entry point, one subcommand per hook event
src/aspark_guard/
  cli.py                  dispatch + the four handlers
  artifacts.py            locating, classifying, hashing, status parsing
  ledger.py               the append-only chain
  drift.py                outside-edit detection
  config.py               .spark/guard.json
  gitinfo.py              the one subprocess
```

---

## Known limits

- **POSIX only.** The hook command is `python3 …`; Windows needs a `py -3` fallback.
- **A determined route around it exists** and always will: a hook cannot distinguish
  "the agent decided this" from "the user dictated it". The goal is not *no override*
  but *no silent override*.
- **The ledger is only as honest as the repo.** Nothing stops a force-push. Integrity
  here rests on git, not on the guard.
- **Not proven in a real project yet.** Everything above is tested; none of it has run
  a full feature loop on someone else's repo.

---

## License

[MIT](LICENSE) © 2026 Andreas Lottes
