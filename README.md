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
that runs **outside** the model, on the tool call itself. Two guarantees:

1. **No gate can be skipped silently.** A write that violates a phase precondition is
   denied before it happens, however good the reasoning behind it sounded.
2. **No override stays invisible.** Gates can be overruled — but only through a dated,
   hash-bound entry in the repo, reviewable in the pull request.

Core is not modified. Nothing here runs unless a project has a `.spark/` directory.

---

## Status

**This is `0.1.0` — the first complete version. All six milestones are built;
what is missing is field evidence, not mechanism.**

| Milestone | What it does | State |
|---|---|---|
| **M0** Skeleton | Plugin manifest, four wired hooks, payload parsing, the silence and fail-open invariants | **Built** |
| **M1** Ledger + drift check | Every `.spark/` write recorded with its SHA-256 and status; artifacts edited outside the loop reported at session start | **Built** |
| **M2** Gate guard | Rules R1–R3 deny writes that violate a phase precondition | **Built** |
| **M3** Override mechanics | R4 plus hash-bound override entries | **Built** |
| **M4** Template validator + trail | Form drift reported as context, never blocked; one trail line per finished subagent | **Built** |
| **M5** Release | Installation proven from the manifest's own command lines; full-cycle test; `docs/evidence.md` | **Built** |

Both guarantees hold for the three rules below, proven by the test suite (222 tests today) and replayed over
22 real gated artifacts without a false positive. Installed from the marketplace and
verified working on 2026-09-11 — see [`docs/evidence.md`](docs/evidence.md) §4.

**The one gap that matters:** none of this has run a full feature loop on a project that
isn't this author's — the same gap aSPARK Core names at the top of its own roadmap, for
the same reason. Only a real run shows whether a rule fires where it should *and* stays
quiet where it shouldn't. [`docs/evidence.md`](docs/evidence.md) is the complete account
of what has and has not been exercised.

---

## What it blocks

Three rules, each derived from aSPARK's own artifact chain (`docs/workflow.md`:
*"Each phase reads the artifact of the previous phase and refuses to start if the gate
isn't met"*). The guard makes that refusal structural instead of instructional.

| Rule | A write to… | is denied while… |
|---|---|---|
| `plan-requires-approved-spec` | `plan.md` | `spec.md` exists and is not `approved` |
| `qa-requires-passed-review` | `qa.md` | `review.md` exists and is not `passed` |
| `release-requires-green-gates` | `release.md` | `review.md` or `qa.md` is not `passed`, or `qa.md` still lists a Blocker whose status is exactly `open` |

A denial names the rule, the state that triggered it, and every way forward:

```
aspark-guard: a release may not be written over a red gate.
  rule:  release-requires-green-gates
  state: .spark/weekly-stats/qa.md still lists 1 open Blocker(s): B1.
  Close the gates first (/increment for the fixes, then /peer-review and /demo-day),
  or record an abort by writing this release with status `aborted`.
  To overrule this, append this line to .spark/weekly-stats/overrides.jsonl YOURSELF
  — not via the agent — and replace <why> with the reason:
    {"ts": "…", "rule": "release-requires-green-gates", "artifact": "qa.md",
     "artifact_sha256": "7d41…", "reason": "<why>", "granted_by": "andreas.lottes"}
  The override lapses as soon as the artifact it names changes.
  If this rule does not fit this project, set it to "warn" or "off" under "rules" in
  .spark/guard.json.
```

### What is deliberately *not* blocked

Every one of these is a decision, not an oversight — and each is tested:

- **A missing prerequisite.** "There is no spec" is indistinguishable from "this
  project doesn't keep one", and aSPARK's skills already refuse to start without their
  input. The guard enforces the *ordering* of a loop being run; it does not mandate
  that the loop be run. `lean-rounds` in aSPARK's own repo is a released feature with
  no `qa.md` at all.
- **An unreadable status.** No parseable header table means no fact to act on.
- **An abort record.** A `release.md` written with status `aborted` passes over red
  gates. Refusing it would block the one artifact that documents why nothing shipped.
- **Anything outside the three gated artifacts** — `spec.md` and `review.md` are inputs
  to a gate, never subject to one; so are evidence notes, the constitution, and all your
  source code.
- **Severity or status wording the template doesn't define.** A Blocker counts as open
  only when its status cell is exactly `open`, which is what the QA template requires
  of every consumer: "a suffixed or renamed value silently drops the finding from every
  open-findings view". Real artifacts carry severities like `Blocker → superseded` and
  statuses like `fixed r6, reconfirmed r8`; neither is open.

---

## Overriding a gate

A gate can be overruled. It cannot be overruled *quietly*.

An override is one line appended to `.spark/<feature>/overrides.jsonl`, naming the rule,
the artifact whose state caused the block, **the SHA-256 that artifact had at that
moment**, and a reason:

```json
{"ts":"2026-09-11T10:02:00Z","rule":"release-requires-green-gates",
 "artifact":"qa.md","artifact_sha256":"7d41…",
 "reason":"AC-3.2 only reproducible on Safari, fix in the next feature, customer informed",
 "granted_by":"andreas.lottes"}
```

Four properties make it worth something:

- **It is bound to content, not to a gate.** Change `qa.md` by one character and the
  override lapses — the thing it described no longer exists. This is stricter than
  adSCAILE's `override_decision_id`, which binds to the gate rather than to what the
  gate was looking at.
- **A reason is structurally required.** The suggested line ships with `<why>`, and an
  entry still carrying the placeholder — or an empty reason — grants nothing. You cannot
  paste your way past a gate.
- **One override settles one artifact.** A release blocked by both a failed review *and*
  a failed QA needs two. The denial then names only what is still open.
- **The agent may not write the file.** Rule `overrides-are-human-only` denies any
  agent write to `overrides.jsonl` and hands back the exact line for you to append
  yourself — an override the agent can grant itself is not an override.

And it stays visible: `guard.py check` reports overridden gates explicitly rather than
counting them as clean.

```
weekly-stats/plan.md: OVERRIDDEN [plan-requires-approved-spec] .spark/weekly-stats/spec.md is `draft`, not `approved`.
checked 3 gated artifacts, 0 would be blocked, 1 overridden
```

**The honest limit.** A hook cannot tell "the agent decided this" from "the user
dictated it" — ask the agent to append the line from a shell and it will. Closing that
would mean policing your own terminal. The goal was never *no override*; it is *no
silent override*, and every route leaves the same dated, content-bound, committed line.
That is exactly as far as adSCAILE's guarantee reaches too: it cannot stop a human from
approving, only from approving without saying why.

---

## What it warns about

aSPARK Core's constitution marks certain structures in `templates/` as **protected**,
because the sibling repo `aspark-graph` parses artifacts shaped by them and raises
`TemplateDriftError` on a mismatch — with no version handshake between the two
(Core's ROADMAP: *Blocked — template-version-marker*). So drift surfaces late, in
another repo, as a structural guess.

The guard checks the same structures on the **producing** side, the moment an artifact
is written, and reports through `additionalContext`. It never blocks — a form question
is not worth a gate, and PostToolUse cannot deny anyway.

| Artifact | Checked once the structure exists |
|---|---|
| `spec.md` | `### US-<n> (<MoSCoW>): <title>`, `- [ ] AC-<n>.<m>: <text>` |
| `plan.md` | the `Task Breakdown` columns `#`, `Task`, `Story`, `Status`, `Definition of Done`; task ids `T<n>` |
| `review.md` | the `Findings` columns `Severity`, `Location`, `Status`; finding ids `F<n>` |
| `qa.md` | a verification table carrying `Spec ID` must also carry `Result` |
| `release.md` | header rows `Status` and `Version` |

Two rules keep it quiet enough to be worth having. **Drift, not completeness** — a
structure is only checked once it has been started, so a spec with no stories yet is
never nagged at. And **extra columns are fine**, which is the consumer's own rule:
`plan.md` already ships two beyond the protected five.

> **It found a real one on its first run.** Over aSPARK's own 44 artifacts it flagged
> exactly one line — `- [ ] AC-2.1a:` in `.spark/situational-lenses/spec.md`. Checked
> against `aspark-graph`'s `_AC_RE`, which requires `AC-<n>.<m>` immediately before the
> colon: the suffixed id matches nothing, so that acceptance criterion is **invisible**
> to every graph query. Not a false positive, and not a rule worth loosening.

### The agent-run trail

`SubagentStop` appends one line per finished subagent to `.spark/.guard/trail.jsonl`:

```json
{"ts":"2026-09-11T09:44:03Z","event":"agent_run","agent_type":"reviewer",
 "agent_id":"sub-1","feature":"weekly-stats","stop_reason":"end_turn","session_id":"abc123"}
```

It exists because aSPARK's own metrics had to reach into Claude Code's session logs to
count role-agent runs — the framework does not record them itself. A line per run makes
that number come from the project.

The agent's output is deliberately **not** recorded. `last_assistant_message` is in the
payload and stays there: the purpose is counting runs, not transcribing work, and a log
that quietly accumulates model output is a liability in a repo.

`feature` is an inference, not an observation — a SubagentStop payload carries no file
path, so it is taken from the last artifact this session wrote. Right in the ordinary
case, null before the session has written anything.

---

## Checking the rules against your own history

```bash
python3 /path/to/aSPARK-guard/bin/guard.py check .
```

Replays all three gate rules over every gated artifact already on disk, read-only.
`guard.py scan .` does the same for the template contract and the ledger. On a
project whose features ran cleanly it prints nothing but a count — **every line it does
print there is a false positive.** Run it before you trust the rules on a real project.

Measured on this author's repos: `aSPARK` — 20 gated artifacts across 8 features,
0 blocked. `aSPARK-graph` — 2 artifacts, 0 blocked.

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

### `.spark/.guard/activity.jsonl` — local, never committed

What the team is doing right now, so a read-only cockpit can show it from the project
alone: whether each session is busy, idle, waiting or ended, and which subagents are
running and for how long. **Metadata only, never content** — no prompt, tool input,
tool output, message or thinking is written; every value is an id the harness assigned,
a timestamp, or drawn from a fixed list — the one exception is the short `task` label
below, which has paths masked. No path is recorded otherwise.

```json
{"v":1,"ts":"2026-09-22T10:00:00.123Z","event":"session_state","session_id":"abc123","state":"busy","reason":"prompt"}
{"v":1,"ts":"2026-09-22T10:00:04.310Z","event":"subagent_start","session_id":"abc123","agent_id":"a26e028603b8b4f58",
 "agent_type":"aspark:product-owner","feature":"weekly-stats","task":"Write the spec"}
{"v":1,"ts":"2026-09-22T10:03:11.902Z","event":"agent_run","session_id":"abc123","agent_id":"a26e028603b8b4f58",
 "agent_type":"aspark:product-owner","feature":"weekly-stats","duration_ms":187592}
```

| `event` | Written on | Fields besides `v`, `ts` (UTC, ms), `session_id` |
|---|---|---|
| `session_state` | `UserPromptSubmit` → `busy`/`prompt`; `Stop` → `idle`/`stop`; `PermissionRequest` → `waiting`/`permission`; `SessionEnd` → `ended`/`clear` \| `prompt_input_exit` \| `logout` \| `other` | `state`, `reason` |
| `subagent_start` | `SubagentStart` | `agent_id`, `agent_type`, `feature`, `task` |
| `agent_run` | `SubagentStop` | `agent_id`, `agent_type`, `feature`, `duration_ms` |

- `task` is the short description the main session gave the run (from the `Agent`
  tool's launch), cleaned to one line of at most 80 characters with any absolute or
  `~/` path replaced by `<path>` — never its prompt. A resumed agent gets no label.
  A launch that names no subagent type counts as `general-purpose`, as its start does.
  It is `null` when there is none, or when two launches of the same type are waiting
  at once and the guard can't tell which start is which.
- `duration_ms` is measured from the latest start of that `agent_id` in the same
  session, for every finish after that start — so a resumed agent, which brings a start
  of its own, gets the length of its latest run only. It is `null` for every finish when
  the start isn't in the log. There is no `stop_reason`: the harness doesn't send one,
  and the guard doesn't make one up. The trail above is unchanged.
- `feature` is the same inference the trail makes, and `null` before the session has
  written an artifact.

**Reading it.** A session's state is its latest `session_state`. Any later line of that
session supersedes `waiting`. Because ordinary tool calls aren't hooked, **`waiting` can
stay on after you have answered**, until the session's next recorded event. A question
Claude asks you (`AskUserQuestion`) is not shown as `waiting`; only a permission dialog
is. Only facts are written: **a session with no `ended` line may have been killed**, and
a subagent start with no `agent_run` is over if its session ended — deciding when a
silent session counts as stale is up to the reader.

**A run can finish more than once.** Claude Code sometimes reports one subagent run as
finished, sends it another message, and reports it finished again — with no new start
in between. Each report gets its own `agent_run` line, and lines already written are
never changed. **The authoritative finish is the latest `agent_run` with the same
`session_id` and `agent_id` after that agent's latest `subagent_start`.** So a run can
briefly show as finished before a later `agent_run` corrects its duration, and the trail
then holds one line per finish. This rule holds for every `v: 1` file, including those
already on disk; `v` stays 1.

`v` goes up whenever an event name, a field or its meaning changes; a reader should
refuse a `v` it doesn't know.

**Bounded and local.** At 2 MB the file rotates to `activity.jsonl.1`, replacing the
previous generation, so at most ~4 MB are ever on disk. Every append and rotation holds
one lock (`activity.lock`), so parallel sessions can't break or lose lines (a line
that can't get the lock within 0.5 s is dropped, not waited for). Next to it,
`activity.pending.jsonl` holds a launch's label until its start arrives — an
unclaimed one is ignored after 60 s. On its first write the guard creates `.spark/.guard/.gitignore`, which
ignores `activity*` and itself — so none of these ever shows up in `git status`, while
the ledger and the trail stay visible and committable. An existing `.gitignore` there is
never touched. `guard.py scan .` shows the log's line count and size;
`"activity": false` switches it off.

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

It ships from the same marketplace as aSPARK itself, so if you already added that one,
step one is done:

```bash
claude plugin marketplace add a-lottes/aSPARK
claude plugin install aspark-guard@aspark
```

Then restart Claude Code. Requires Python 3.11+ on `PATH` as `python3`. POSIX only for
now (macOS, Linux) — see *Known limits*.

Check that it sees your project:

```bash
python3 /path/to/aSPARK-guard/bin/guard.py scan .
```

**Recommended, once per project** — the committed logs are append-only, so a conflict
between two branches is never a conflicting edit, only a conflicting file:

```bash
printf '.spark/.guard/ledger.jsonl merge=union\n.spark/.guard/trail.jsonl merge=union\n' >> .gitattributes
```

The activity log isn't committed, so it needs no merge rule.

The guard will not write this for you. It never touches anything outside `.spark/`.

---

## Configuration

Optional, at `.spark/guard.json`. Absent or malformed means these defaults:

```jsonc
{
  "enabled": true,
  "ledger": true,          // record writes            (M1)
  "drift_check": true,     // report outside edits     (M1)
  "trail": true,           // agent-run trail          (M4)
  "activity": true,        // live activity log        (activity-trail)
  "template_check": true,  // template contract        (M4)
  "rules": {               // "block" | "warn" | "off"
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
   directory, and it is the honest price of the current design. The activity log adds
   5 hook events and 1 matcher (9 events, 10 entries in all): per prompt
   `UserPromptSubmit` and `Stop`, per subagent the `Agent` launch and `SubagentStart`
   (`SubagentStop` was already hooked for the trail), plus each permission dialog and
   session end — none on ordinary tool calls. **The guard's own share per activity
   hook, after the interpreter has started:** about 1 ms median (≤ 7 ms p95) in a project
   with `.spark/`, 0.3 ms without one, and at most 16 ms for `SubagentStart`/`SubagentStop`
   with the log at its 2 MB mark — measured in-process on an Intel Core i5-7360U under
   load average ~6–7, `python3` 3.9.6. The process around it costs what every hook costs
   there (~170 ms median, unchanged against `main`). Commands and figures:
   [`docs/evidence.md`](docs/evidence.md) §9.
4. **Never block silently.** Every denial names the rule, the state that triggered it,
   and the way forward. A block with no way out only teaches people to route around it.
5. **State and form only, never quality.** Anything requiring judgment belongs to the
   agents.
6. **No network, no LLM, no dependency.**

Point 6 is not aesthetics. Plugin hooks **bypass the workspace-trust prompt**, so this
code runs on other people's machines unasked. It stays standard-library-only and
readable in one sitting so that it can be audited by the people it runs for:
**2,016 lines** in `src/aspark_guard/` (`wc -l`, 2026-09-23; it was "under a thousand"
once and isn't any more). The only subprocess it ever spawns is `git rev-parse --short HEAD`.

---

## Development

```bash
python3 -m unittest discover -s tests -t tests
```

222 tests, no dependencies, no network, no Claude Code required. Three layers:

- **Behaviour against fixtures** — one artifact state per fixture: draft, approved,
  uninstantiated template, broken header table.
- **Hook contract tests** (`tests/fixtures/payloads/`, `test_install.py`) — recorded
  payloads in the shape Claude Code documents, plus the manifest's own command lines run
  through a shell from a path containing a space. An API change surfaces here rather
  than as a plugin that silently stopped working.
- **Fail-open tests** — every hostile input we could think of must yield exit 0 and no
  output.

`test_end_to_end.py` runs one feature through the whole cycle with all four mechanisms
live, because the unit tests each prove one rule and none of them proves they compose.
See [CONTRIBUTING.md](CONTRIBUTING.md) before adding a rule — the false-positive check
against real history is not optional.

```
bin/guard.py              one entry point, one subcommand per hook event
src/aspark_guard/
  cli.py                  dispatch + one handler per hook event
  artifacts.py            locating, classifying, hashing, status parsing
  ledger.py               the append-only chain
  drift.py                outside-edit detection
  overrides.py            reading, matching and suggesting override entries
  templates.py            the protected template structures
  trail.py                one line per finished subagent
  activity.py             the live activity log: lock, rotation, pairing, labels
  config.py               .spark/guard.json
  gitinfo.py              the one subprocess
```

---

## Known limits

- **POSIX only.** The hook command is `python3 …`; Windows needs a `py -3` fallback, and
  the activity log's lock uses `fcntl`, which Windows doesn't have.
- **A determined route around it exists** and always will: a hook cannot distinguish
  "the agent decided this" from "the user dictated it". See *Overriding a gate*.
- **The ledger is only as honest as the repo.** Nothing stops a force-push. Integrity
  here rests on git, not on the guard.
- **~50 ms on every `Write`/`Edit`, everywhere** — including repos with no `.spark/`
  directory, where the guard does nothing. Mostly Python interpreter startup. This is
  the strongest argument against installing it. The activity hooks add the same per
  prompt, per turn end and per subagent (see *Invariants*, point 3).
- **Untested: concurrent sessions on the ledger.** Two agents writing `.spark/` at once
  both append to the ledger; POSIX append should keep whole lines intact, but that has
  not been shown. The activity log is locked and tested with two writers across a
  rotation.
- **`waiting` is coarse.** It comes from permission dialogs only, and can outlive your
  answer until the session's next hooked event (see *What it records*).
- **Not proven in a real project yet.** Everything above is tested; none of it has run a
  full feature loop on someone else's repo. [`docs/evidence.md`](docs/evidence.md) lists
  exactly what has and has not been exercised.

---

## License

[MIT](LICENSE) © 2026 Andreas Lottes
