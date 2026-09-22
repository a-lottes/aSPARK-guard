# Evidence — v0.1.0

What has actually been exercised, and what has not. Every number here was produced by
a command written next to it, so it can be re-run rather than believed.

Date: 2026-09-11 · one machine (macOS, Apple silicon, Python 3.13)

---

## 1. The test suite

```bash
python3 -m unittest discover -s tests -t tests
```

**142 tests, 0 failures.** No dependencies, no network, no Claude Code session
required. Three layers, per the plan's §9:

| Layer | Files | What it can and cannot show |
|---|---|---|
| Behaviour against fixtures | `test_artifacts`, `test_rules`, `test_templates`, `test_overrides`, `test_ledger`, `test_drift`, `test_trail` | Each rule and parser against one artifact state per fixture. Cannot show that the states are the ones real projects produce — §2 covers that |
| Hook contract | `test_hook_contract`, `test_gate_hook`, `test_install` | The documented payload shapes, the decision JSON, and the manifest's own command lines. Cannot show the harness still sends those shapes tomorrow |
| Fail-open | `test_failopen`, `test_negative_case` | Every hostile input we thought of yields exit 0 and no output. Cannot show we thought of all of them |

The negative case runs first, as aSPARK Core's constitution requires of an optional
capability: in a repo with no `.spark/` directory, all four events are silent and no
file is created (`test_negative_case.py`).

---

## 2. Dogfood against real projects

The gate rules and the template check were replayed over artifacts that real cycles
produced. Read-only: `git status --porcelain` in both repos was empty before and after.

```bash
python3 bin/guard.py check ~/aSPARK       # gate rules
python3 bin/guard.py scan  ~/aSPARK       # template contract, ledger, drift
```

| Repo | Gated artifacts | Would be blocked | Artifacts scanned | Template findings |
|---|---:|---:|---:|---:|
| `aSPARK` (8 features) | 20 | **0** | 44 | **1** |
| `aSPARK-graph` | 2 | **0** | 8 | 0 |

**0 false positives on the gate rules** — the acceptance condition for M2. Every one of
those 22 artifacts came from a cycle that ran cleanly, so any block would have been a
false positive by definition.

### The one template finding is real

```
~ .spark/situational-lenses/spec.md: acceptance criterion is not `- [ ] AC-<n>.<m>: <text>`,
  so aspark-graph will not see it at all: '- [ ] AC-2.1a: Given an active **Review-owned** lens…'
```

Verified against the consumer rather than assumed. `aspark-graph`'s
`src/aspark_graph/artifacts.py:40`:

```python
_AC_RE = re.compile(r"^\s*-\s*\[[ xX]?\]\s*(AC-\d+\.\d+)\s*:\s*(.+?)\s*$")
```

`AC-<n>.<m>` must be followed immediately by the colon. In `AC-2.1a:` it is followed by
`a`, so the line matches nothing — the criterion is invisible to every graph query, and
nothing anywhere reports that. Not a false positive; the rule was sharpened rather than
loosened.

Four other `AC-\d+\.\d+[a-z]` hits in the same repo are prose inside table cells, which
the check correctly ignores — the trigger is the checkbox, not the identifier.

---

## 3. Three real-project findings that shaped the design

Each of these came from reading real artifacts, and each changed a rule:

| Found in | What it showed | What changed |
|---|---|---|
| `handbook-maturity/release.md` | A status cell annotated with further backticked values: ``​`handed-off` (`pr` mode — …)`` | Templates are told apart from annotation by *shape*, not by counting backticks. Before the fix, a plainly stated status parsed as unknown |
| `lean-rounds/` | A released feature with `review.md` and `release.md` but **no `qa.md` at all** | A missing prerequisite never blocks. Had "absent = block" shipped, this would have been a false positive on a clean feature |
| several `qa.md` | Severities like `Blocker → superseded`, statuses like `fixed r6, reconfirmed r8` | Severity matched loosely, status matched strictly against exactly `open` — which is what the QA template requires of every consumer |

---

## 4. Installation

`tests/test_install.py` reads `hooks/hooks.json`, substitutes `${CLAUDE_PLUGIN_ROOT}`
the way the harness does, and runs the resulting command lines **through a shell** —
from a plugin directory named `plugin cache/aspark guard` and a project named
`someone elses project`, because that is where naive quoting breaks.

Proven there:

- all four commands exit 0 with empty stderr;
- a fresh install needs no setup — no config file, no directory created by hand, no
  build step: the first write creates the ledger and records a parsed status;
- the gate denies through the real command line, not just through `cli.main`;
- an unrelated repo with no `.spark/` is byte-for-byte untouched after all four events;
- only `bin/` and `src/` are copied, so nothing reaches for tests or docs at runtime.

```bash
claude plugin validate .    # ✔ Validation passed
```

### Published and re-verified from GitHub, 2026-09-11

The repository is public at `a-lottes/aSPARK-guard` (`v0.1.0`), and the marketplace entry
naming it is on `a-lottes/aSPARK`'s `main`. Verified from a clone rather than from the
working copy:

```bash
git clone https://github.com/a-lottes/aSPARK-guard.git
cd aSPARK-guard && python3 -m unittest discover -s tests -t tests   # 142 tests, OK
claude plugin validate .                                            # ✔ Validation passed
```

So what is published is complete and runs on its own.

### Installed from the marketplace, 2026-09-11

```bash
claude plugin marketplace update aspark
claude plugin install aspark-guard@aspark
claude plugin list          # aspark-guard@aspark · 0.1.0 · user · ✔ enabled
```

The installed copy lands at
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` — the plugin root is
**versioned**, so `${CLAUDE_PLUGIN_ROOT}` resolves to `…/aspark-guard/0.1.0`, not to
`…/aspark-guard`.

Its own four hook commands were then run through a shell against a throwaway project,
from that installed path rather than from a checkout:

| Event | exit | stderr | result |
|---|---:|---|---|
| `PostToolUse` | 0 | empty | ledger created: `.spark/demo/spec.md \| draft \| 0efb43869413 \| product-owner` |
| `PreToolUse` | 0 | empty | `deny` — *a plan may not be written while the spec is not approved* |
| `SessionStart` | 0 | empty | silent (nothing to report) |
| `SubagentStop` | 0 | empty | silent |

That closes the M5 definition of done: **installed from the marketplace into a project
that had nothing set up, and working, with no further configuration.**

**Still not exercised:** the hooks firing inside a live Claude Code session. Plugins
activate on session start, so a session already running when the plugin was installed
does not yet carry them. Everything above drives the same commands the harness would,
but by hand.

---

## 5. Cost

```bash
# 20 invocations, PreToolUse on a file outside .spark/
```

**~50 ms per invocation** (pre 52 ms, post 47 ms), of which roughly 40 ms is the Python
interpreter starting. This is paid on **every** `Write`/`Edit` in every project,
including ones with no `.spark/` directory, where the guard does nothing at all. It is
the honest price of a hook that shells out to Python, and the single strongest argument
for anyone who decides not to install this.

---

## 6. What is not proven

- **No full loop on a project that is not this author's.** Same gap aSPARK Core names
  at the top of its own roadmap, for the same reason: only a real run tells you whether
  a rule fires where it should and stays quiet where it shouldn't.
- **No Windows.** The hook command is `python3 …`; nothing here has run on Windows.
- **No concurrent sessions.** Two agents writing `.spark/` at once would both append to
  the ledger. POSIX append should keep whole lines intact; that has not been tested.
- **The trail's `feature` field is an inference**, taken from the last artifact the
  session wrote, and will be wrong for an agent that runs across two features in one
  session.
- **Overrides can still be routed around** by asking the agent to append the line from a
  shell. Documented in the README rather than closed, because closing it means policing
  the user's own terminal.

---

## 7. Hook spike (activity-trail T1, 2026-09-22)

Settles risk A3 of `.spark/activity-trail/spec.md`: which hook events a **plugin** receives,
and what their payloads carry. Run against `claude --version` → `2.1.280 (Claude Code)`,
macOS.

**Probe.** A throwaway plugin (deleted after the run) registered one command hook on each of
`UserPromptSubmit`, `Stop`, `Notification`, `PermissionRequest`, `SubagentStart`,
`SubagentStop`, `SessionStart`, `SessionEnd`, `PreCompact`, plus `PreToolUse`/`PostToolUse`
matching `Task|Agent|AskUserQuestion`. It appended key names, enum-like values, ids, string
**lengths** and a wall-clock ms stamp to a scratch file outside any repo — never content.
Loaded with `claude --plugin-dir <probe>`, in an empty scratch directory:

1. headless: `claude -p --plugin-dir <probe> "<launch 2 parallel general-purpose agents, then resume one via SendMessage>"`;
2. interactive, driven by the author: Bash commands answered at the permission prompt, ≥ 90 s idle, `/clear`, `/exit`;
3. headless: a request to call `AskUserQuestion`.

**What fired, and what it carries**

| Event | Fired as plugin hook | Relevant keys (besides `session_id`, `cwd`, `transcript_path`, `prompt_id`) |
|---|---|---|
| `UserPromptSubmit` | yes (headless + interactive) | `prompt` (content — never read), `permission_mode` |
| `Stop` | yes | `last_assistant_message` (content), `stop_hook_active`, `background_tasks`, `session_crons` |
| `SubagentStart` | yes | `agent_id`, `agent_type` — **no** description, **no** `tool_use_id` |
| `SubagentStop` | yes | `agent_id`, `agent_type`, `agent_transcript_path`, `last_assistant_message` — **no `stop_reason`** |
| `PreToolUse` on the subagent tool | yes | `tool_name` is **`Agent`**; `tool_input` has `description`, `prompt`, `subagent_type`, `run_in_background`; `tool_use_id` |
| `Notification` | yes (interactive only) | `notification_type`, `message` (content) |
| `PermissionRequest` | yes (interactive only) | `tool_name`, `tool_input`, `permission_suggestions` |
| `SessionEnd` | yes | `reason` |

**Findings**

- **Pairing by `agent_id` holds.** Two parallel runs of the same type got distinct ids, and
  each `SubagentStop` carried its own start's id. A run resumed through `SendMessage` fires a
  **new `SubagentStart` with the same `agent_id`**, then its own stop — so "latest unmatched
  start" (plan D3) measures only the resumed run.
- **Harness-internal subagents.** The interactive session produced three `SubagentStop`
  events with `agent_type: ""` and **no** `SubagentStart` before them. The existing trail
  already skips an empty `agent_type`; activity must do the same, or every such stop becomes a
  `duration_ms: null` run.
- **Notification types observed:** `permission_prompt` and `idle_prompt`. `idle_prompt`
  arrived ~60 s after the last `Stop`, twice in one idle stretch. No other type was seen.
- **`permission_prompt` is late.** It fired **5.98 s** after the matching `PermissionRequest`,
  and only for a prompt still unanswered at that point; the four prompts answered within
  ~3 s produced a `PermissionRequest` but **no** `permission_prompt` notification.
  `PermissionRequest` fires when the dialog is raised. Screen-vs-hook latency was not
  measured with a clock on the screen; `PermissionRequest` is the earliest signal available.
- **`AskUserQuestion` not observed.** The tool is unavailable in `-p` mode (the model
  replied "no tool"), and in the interactive run it was not called. No `PreToolUse`, no
  notification type for a question was recorded.
- **`SessionEnd.reason` values:** `clear` (`/clear`), `prompt_input_exit` (`/exit`),
  `other` (end of a `-p` run). `/clear` is followed at once by a `SessionStart` with
  `source: "clear"` and a **new** `session_id`.
- **Synthetic prompts.** A resumed background agent's result was delivered back into the
  headless session as a prompt and fired `UserPromptSubmit` (`busy/prompt`) with no user
  involved.

**T1 outcome table** (plan §3)

| Row | Result |
|---|---|
| UserPromptSubmit / Stop delivered to plugin hooks | **Go** |
| SubagentStart available | **Go** — no description on it, so the label comes from `PreToolUse` on `Agent` (plan D6 pending-file variant) |
| `agent_id` equal between Start and Stop | **Go** (parallel same-type and resumed run both checked) |
| Notification type tells a prompt from an idle reminder | **Go** for the type field (`permission_prompt` vs `idle_prompt`) — but see timing row |
| Permission notification within 2 s of the prompt | **Degrade** for `Notification` (5.98 s, and absent when answered within ~6 s). `PermissionRequest` fires at dialog time → proposed as the source of `waiting/permission` (deviation D-T1-1) |
| AskUserQuestion fires a distinguishable signal | **Degrade** — not observable here; `question` is not recorded this cycle (reasons are "e.g." in AC-1.3) |
| SessionEnd available | **Go** — reasons `clear`, `prompt_input_exit`, `other` |
| Short description in the subagent tool's input | **Go** — `tool_input.description` |

**Fixtures.** Redacted payloads with the observed key sets, content replaced by marker
strings, paths by `__ROOT__`: `tests/fixtures/payloads/{user_prompt_submit,stop,notification_permission,notification_idle,permission_request,subagent_start,subagent_stop_internal,session_end,pre_tool_use_task}.json`.

---

## 8. Activity-trail cost and final counts (T12, 2026-09-22)

Machine: Intel Core i5-7360U (2 cores), macOS, **heavily loaded** — load average 7–105
during the runs. Hooks run under the machine's `python3`, here `/usr/bin/python3`
3.9.6. Every number below comes from:

```bash
/usr/bin/python3 tests/bench_hooks.py 50 /usr/bin/python3
```

**Per invocation, as the harness pays it** (own process, payload on stdin; second run, load ≈ 7–9):

| | median | p95 | max |
|---|---|---|---|
| bare interpreter start (`python3 -c pass`) | 78 ms | 111 ms | 147 ms |
| new activity hooks, project with `.spark/` | 202–233 ms | 292–378 ms | 302–626 ms |
| new activity hooks, project without `.spark/` | 194–246 ms | 241–462 ms | 296–682 ms |
| new activity hooks, log at the 2 MB mark | 197–257 ms | 219–381 ms | 279–559 ms |
| existing gate/ledger hooks (`Write`), same run | 205–227 ms | 296–489 ms | 350–566 ms |

**Before vs after, interleaved** (60 runs each, same shell, `git worktree` at `208a00c`):
`pre-tool-use` 219 → 203 ms median, `post-tool-use` 210 → 216 ms median. No regression
beyond noise.

**The guard's own share, in-process** (handler only, after import): `user-prompt-submit`,
`stop`, `subagent-start` ≈ 1 ms median / ≤ 6 ms p95; `subagent-stop` 4 ms median. At the
2 MB mark, with realistic agent ids, the pairing scan over both generations costs
`subagent-stop` **12 ms median / 16 ms p95 / 18 ms max**. Importing `aspark_guard.cli`
costs 85–140 ms here (`python3 -X importtime`), paid by every hook, old and new.

**Verdict on NFR-1 (p95 ≤ 100 ms, max ≤ 500 ms): not met on this machine, and not
attributable to this feature.** The bare interpreter's own p95 (111 ms) is already above
the bound, and the pre-existing hooks miss it by the same margin as the new ones. The
activity work itself is ≤ 16 ms p95. The absolute bound needs a re-run on an unloaded
machine (the 47 ms figure in §5 came from an M-series Mac).

**Added cost per unit of work, projects without `.spark/` included:** each prompt now
pays 2 extra hook starts (`UserPromptSubmit`, `Stop`); each subagent 3 (`Agent` launch,
`SubagentStart`, `SubagentStop`); each permission dialog and each session end 1. On this
machine that is ~200 ms per start; on the M-series figure of §5, ~50 ms.

**Counts.** Full suite: **206 tests, OK** (`python3.13 -m unittest discover -s tests`;
the suite needs ≥ 3.10, see plan D-T1-5). `wc -l src/aspark_guard/*.py` → **1,980**
lines, as stated in the README. The only edited existing assertion is `EXPECTED_EVENTS`
in `tests/test_install.py` (plan ruling Q1).
