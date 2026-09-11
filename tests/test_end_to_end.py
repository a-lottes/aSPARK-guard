"""One feature through the whole loop, with all four mechanisms live.

The unit tests each prove one rule. This proves they compose: that a plausible
sequence of writes produces the blocks, the ledger chain, the override, the trail
and the drift notice in the order a real cycle would.
"""

import json
import unittest

from support import GuardTestCase
from aspark_guard import artifacts, overrides, rules


class TestOneFeatureEndToEnd(GuardTestCase):
    FEATURE = "weekly-stats"

    def setUp(self):
        super().setUp()
        self.make_spark_project()

    # --- helpers ------------------------------------------------------------

    def path(self, name):
        return self.root / ".spark" / self.FEATURE / name

    def author(self, name, text, agent="product-owner"):
        """Write an artifact the way a ceremony would: gate first, then record."""
        allowed, decision = self.attempt(name)
        if not allowed:
            return False, decision
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.post_tool_use(path, agent_type=agent)
        return True, decision

    def attempt(self, name, content=None):
        tool_input = {"file_path": str(self.path(name))}
        if content is not None:
            tool_input["content"] = content
        _, out = self.run_hook("pre-tool-use", {
            "session_id": "test-session",
            "cwd": str(self.root),
            "tool_name": "Write",
            "tool_input": tool_input,
        })
        if not out.strip():
            return True, None
        specific = json.loads(out)["hookSpecificOutput"]
        return specific.get("permissionDecision") != "deny", specific

    def header(self, kind, status):
        return f"# {kind}: {self.FEATURE}\n\n| | |\n|---|---|\n| **Status** | `{status}` |\n"

    # --- the cycle ----------------------------------------------------------

    def test_the_loop_holds_together(self):
        # Specify --------------------------------------------------------
        ok, _ = self.author("spec.md", self.header("Spec", "draft"))
        self.assertTrue(ok, "writing a draft spec is never gated")

        # Plan -----------------------------------------------------------
        ok, decision = self.attempt("plan.md")
        self.assertFalse(ok, "the plan gate must hold against a draft spec")
        self.assertIn(rules.R_PLAN, decision["permissionDecisionReason"])

        self.author("spec.md", self.header("Spec", "approved"))
        ok, _ = self.author("plan.md", self.header("Plan", "approved"),
                            agent="engineering-manager")
        self.assertTrue(ok, "an approved spec opens the plan gate")

        # Review ---------------------------------------------------------
        ok, decision = self.attempt("qa.md")
        self.assertTrue(ok, "with no review on disk, nothing is known and nothing blocks")

        self.author("review.md", self.header("Review", "passed"), agent="reviewer")

        # QA, with one blocker still open --------------------------------
        self.author(
            "qa.md",
            self.header("QA", "passed")
            + "\n| # | Severity | Steps | Expected vs. observed | Status |\n"
            "|---|---|---|---|---|\n| B1 | Blocker | refresh | data lost | open |\n",
            agent="qa-tester",
        )

        # Keep -----------------------------------------------------------
        ok, decision = self.attempt("release.md")
        self.assertFalse(ok, "an open Blocker must hold the release gate")
        reason = decision["permissionDecisionReason"]
        self.assertIn("B1", reason)
        self.assertIn(overrides.OVERRIDES_FILE, reason)

        # The agent may not clear its own way -----------------------------
        ok, decision = self.attempt(overrides.OVERRIDES_FILE)
        self.assertFalse(ok)
        self.assertIn(rules.R_OVERRIDE, decision["permissionDecisionReason"])

        # ... so the human appends the offered line, with a reason --------
        offered = json.loads(
            [line.strip() for line in reason.splitlines() if line.strip().startswith("{")][0]
        )
        offered["reason"] = "B1 is a Safari-only repro; shipping, fix scheduled next cycle"
        with open(self.path(overrides.OVERRIDES_FILE), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(offered) + "\n")

        ok, _ = self.author("release.md", self.header("Release", "released"),
                            agent="release-manager")
        self.assertTrue(ok, "the override opens the release gate")

        # What the repo now knows ----------------------------------------
        written = [entry["path"] for entry in self.ledger_entries()]
        self.assertEqual(
            written,
            [
                ".spark/weekly-stats/spec.md",   # draft
                ".spark/weekly-stats/spec.md",   # approved — the chain, not a diff
                ".spark/weekly-stats/plan.md",
                ".spark/weekly-stats/review.md",
                ".spark/weekly-stats/qa.md",
                ".spark/weekly-stats/release.md",
            ],
        )
        self.assertEqual(
            [e["status"] for e in self.ledger_entries()],
            ["draft", "approved", "approved", "passed", "passed", "released"],
        )

        # The override is visible, not swallowed --------------------------
        import io
        from contextlib import redirect_stdout
        from aspark_guard import cli

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["check", str(self.root)])
        self.assertIn("OVERRIDDEN", buffer.getvalue())
        self.assertIn("1 overridden", buffer.getvalue())

        # A human edit outside the loop is reported ------------------------
        self.assertEqual(self.session_start()[1], "", "clean before the edit")
        spec = self.path("spec.md")
        spec.write_text(spec.read_text(encoding="utf-8") + "\nLate addition.\n",
                        encoding="utf-8")
        notice = self.session_start()[1]
        self.assertIn("spec.md", notice)
        self.assertIn("outside the loop", notice)

    def test_the_same_cycle_records_its_agent_runs(self):
        for role in ("product-owner", "engineering-manager", "reviewer",
                     "qa-tester", "release-manager"):
            self.run_hook("subagent-stop", {
                "session_id": "test-session",
                "cwd": str(self.root),
                "agent_type": role,
                "stop_reason": "end_turn",
            })

        trail = self.root / ".spark" / ".guard" / "trail.jsonl"
        runs = [json.loads(line) for line in trail.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(runs), 5)

    def test_nothing_the_guard_wrote_is_itself_gated(self):
        # The guard's own files must never trip its own rules.
        for name in ("ledger.jsonl", "trail.jsonl"):
            path = self.root / ".spark" / ".guard" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
            self.assertIsNone(rules.evaluate(self.root, path))
            self.assertFalse(artifacts.is_spark_artifact(path, self.root))


if __name__ == "__main__":
    unittest.main()
