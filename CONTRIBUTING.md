# Contributing

This plugin runs on other people's machines from a hook, **without a trust prompt**.
That single fact decides most of what follows.

## The rules that are not negotiable

1. **Standard library only.** No dependencies, no build step, no lockfile. A reader has
   to be able to audit the whole thing in one sitting.
2. **No network. No LLM.** The only subprocess is `git rev-parse` / `git config`.
3. **Fail open.** Every new code path must let the action proceed when it is unsure.
   A guard that blocks on its own confusion gets switched off, and then it guards
   nothing.
4. **Degrade to silence.** Nothing runs, prints or writes in a repo with no `.spark/`
   directory.
5. **Nothing outside `.spark/` is ever written.** Not `.gitattributes`, not config, not
   a marker file. Suggest it in the README instead.
6. **State and form only, never quality.** Anything requiring judgment belongs to
   aSPARK's agents, not here.

## Adding a rule

A new gate rule is only worth shipping if it can be decided from files on disk, without
knowing which ceremony is running. If it needs to know that, a hook cannot enforce it.

Before opening a PR, run it against real history:

```bash
python3 bin/guard.py check /path/to/a/real/aspark/project
```

**Every line it prints on a project whose features ran cleanly is a false positive**, and
false positives are the only failure mode that can kill this tool — one bad block and
the user sets `enabled: false` forever. Fix them before the rule ships, and record the
run in `docs/evidence.md`.

New rules ship in the config with a mode, so a project that disagrees can downgrade them
to `warn` or `off` rather than disabling everything.

## Tests

```bash
python3 -m unittest discover -s tests -t tests
```

No pytest, no runner to install. Three layers, and a change usually needs all three:

- **Behaviour** against a fixture in `tests/fixtures/artifacts/` — one file per artifact
  state, including the malformed ones.
- **Hook contract** in `tests/test_hook_contract.py` and `tests/test_install.py` —
  recorded payloads, and the manifest's own command lines executed through a shell.
  These are what catch a change in the harness rather than in this code.
- **Fail-open** in `tests/test_failopen.py` — add the hostile input your change makes
  possible.

If you touch anything a real project's artifacts flow through, add the real-world shape
as a fixture. Three of this repo's rules exist in their current form because a real
artifact disagreed with the obvious implementation; those cases are listed in
`docs/evidence.md` §3.

## Honesty about maturity

Borrowed from aSPARK Core's constitution, and meant literally: **a thing is shipped when
it has been exercised, not when it has been written.** The README's status table and
`docs/evidence.md` say what has actually run. A doc that presents an intention as
delivered is a defect, not a rounding error.

If you run this on a real project — especially if it went badly — that report is worth
more than a patch.
