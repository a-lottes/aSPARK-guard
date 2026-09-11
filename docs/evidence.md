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

**Still not exercised:** `claude plugin install aspark-guard@aspark` in a live session.
The source now resolves and the manifests validate, but installing changes the behaviour
of every subsequent session on that machine, so it is the user's call to make rather
than something to verify in passing.

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
