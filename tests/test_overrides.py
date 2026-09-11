"""Overrides (M3): the documented way past a closed gate, and only that way."""

import json
import re
import unittest

from support import GuardTestCase
from aspark_guard import artifacts, overrides, rules


class OverrideTestCase(GuardTestCase):
    FEATURE = "weekly-stats"

    def setUp(self):
        super().setUp()
        self.make_spark_project()

    def place(self, name: str, fixture: str):
        return self.write_fixture_artifact(f".spark/{self.FEATURE}/{name}", fixture)

    def target(self, name: str):
        return self.root / ".spark" / self.FEATURE / name

    def sha_of(self, name: str) -> str:
        return artifacts.sha256_file(self.target(name))

    def grant(self, rule: str, artifact: str, reason: str = "customer signed off",
              sha: str | None = None):
        entry = {
            "ts": "2026-09-11T10:00:00Z",
            "rule": rule,
            "artifact": artifact,
            "artifact_sha256": sha if sha is not None else self.sha_of(artifact),
            "reason": reason,
            "granted_by": "andreas",
        }
        path = self.root / ".spark" / self.FEATURE / overrides.OVERRIDES_FILE
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return entry

    def pre_tool_use(self, name: str, content: str | None = None):
        tool_input = {"file_path": str(self.target(name))}
        if content is not None:
            tool_input["content"] = content
        return self.run_hook("pre-tool-use", {
            "session_id": "test-session",
            "cwd": str(self.root),
            "tool_name": "Write",
            "tool_input": tool_input,
        })

    def decision(self, out: str) -> dict:
        return json.loads(out)["hookSpecificOutput"]


class TestOverrideLiftsTheBlock(OverrideTestCase):
    def setUp(self):
        super().setUp()
        self.place("spec.md", "spec_draft.md")

    def test_without_an_override_the_plan_is_denied(self):
        self.assertIsNotNone(rules.evaluate(self.root, self.target("plan.md")))

    def test_a_usable_override_lets_the_write_through(self):
        self.grant(rules.R_PLAN, "spec.md")
        self.assertIsNone(rules.evaluate(self.root, self.target("plan.md")))
        self.assertEqual(self.pre_tool_use("plan.md"), (0, ""))

    def test_changing_the_artifact_lapses_the_override(self):
        self.grant(rules.R_PLAN, "spec.md")
        self.assertIsNone(rules.evaluate(self.root, self.target("plan.md")))

        # One more sentence in the spec and the override no longer describes it.
        spec = self.target("spec.md")
        spec.write_text(spec.read_text(encoding="utf-8") + "\nA late addition.\n",
                        encoding="utf-8")

        self.assertIsNotNone(rules.evaluate(self.root, self.target("plan.md")))

    def test_an_override_for_another_rule_or_artifact_does_nothing(self):
        self.grant(rules.R_QA, "spec.md")
        self.assertIsNotNone(rules.evaluate(self.root, self.target("plan.md")))

        self.place("review.md", "review_passed.md")
        self.grant(rules.R_PLAN, "review.md")
        self.assertIsNotNone(rules.evaluate(self.root, self.target("plan.md")))

    def test_an_unfilled_or_empty_reason_grants_nothing(self):
        # The suggested line ships with a placeholder; pasting it unchanged must not
        # count as having given a reason.
        self.grant(rules.R_PLAN, "spec.md", reason=overrides.REASON_PLACEHOLDER)
        self.assertIsNotNone(rules.evaluate(self.root, self.target("plan.md")))

        self.grant(rules.R_PLAN, "spec.md", reason="   ")
        self.assertIsNotNone(rules.evaluate(self.root, self.target("plan.md")))

    def test_a_wrong_hash_grants_nothing(self):
        self.grant(rules.R_PLAN, "spec.md", sha="0" * 64)
        self.assertIsNotNone(rules.evaluate(self.root, self.target("plan.md")))


class TestPastingTheSuggestedLineWorks(OverrideTestCase):
    """End to end: the line the denial offers must actually lift that denial."""

    def test_the_offered_line_lifts_the_block_once_a_reason_is_written(self):
        self.place("spec.md", "spec_draft.md")
        _, out = self.pre_tool_use("plan.md")
        reason_text = self.decision(out)["permissionDecisionReason"]

        self.assertIn("append this line", reason_text)
        self.assertIn("YOURSELF", reason_text)

        offered = re.search(r"^\s*(\{.*\})\s*$", reason_text, re.MULTILINE)
        self.assertIsNotNone(offered, reason_text)

        entry = json.loads(offered.group(1))
        self.assertEqual(entry["rule"], rules.R_PLAN)
        self.assertEqual(entry["artifact"], "spec.md")
        self.assertEqual(entry["artifact_sha256"], self.sha_of("spec.md"))
        self.assertEqual(entry["reason"], overrides.REASON_PLACEHOLDER)

        # Pasted unchanged, it still grants nothing.
        path = self.root / ".spark" / self.FEATURE / overrides.OVERRIDES_FILE
        path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        self.assertIn("deny", self.pre_tool_use("plan.md")[1])

        # With a reason filled in, the write goes through.
        entry["reason"] = "spec approval is waiting on legal; planning starts now"
        path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        self.assertEqual(self.pre_tool_use("plan.md"), (0, ""))


class TestPartialOverrides(OverrideTestCase):
    def test_each_red_gate_needs_its_own_override(self):
        self.place("review.md", "review_open.md")
        self.place("qa.md", "qa_failed.md")

        violation = rules.evaluate(self.root, self.target("release.md"))
        self.assertEqual(len(violation.triggers), 2)

        self.grant(rules.R_RELEASE, "review.md")
        partial = rules.evaluate(self.root, self.target("release.md"))
        self.assertIsNotNone(partial, "one override must not clear both gates")
        self.assertEqual([t.artifact for t in partial.triggers], ["qa.md"])

        self.grant(rules.R_RELEASE, "qa.md")
        self.assertIsNone(rules.evaluate(self.root, self.target("release.md")))

    def test_one_artifact_failing_twice_needs_one_override(self):
        # qa.md that is both `failed` and carries an open Blocker is still one
        # artifact in one state.
        self.place("review.md", "review_passed.md")
        self.write_artifact(
            f".spark/{self.FEATURE}/qa.md",
            "| **Status** | `failed` |\n\n"
            "| # | Severity | Steps | Expected vs. observed | Status |\n"
            "|---|---|---|---|---|\n"
            "| B1 | Blocker | x | y | open |\n",
        )

        violation = rules.evaluate(self.root, self.target("release.md"))
        self.assertEqual(len(violation.triggers), 1)
        self.assertIn("open Blocker", violation.state)

        self.grant(rules.R_RELEASE, "qa.md")
        self.assertIsNone(rules.evaluate(self.root, self.target("release.md")))


class TestOverridesAreHumanOnly(OverrideTestCase):
    def test_an_agent_write_to_the_override_file_is_denied(self):
        self.place("spec.md", "spec_draft.md")
        code, out = self.pre_tool_use(overrides.OVERRIDES_FILE)

        decision = self.decision(out)
        self.assertEqual(code, 0)
        self.assertEqual(decision["permissionDecision"], "deny")

        reason = decision["permissionDecisionReason"]
        self.assertIn(rules.R_OVERRIDE, reason)
        self.assertIn("not an override", reason)
        # It offers the line for whatever is actually blocked right now.
        self.assertIn(rules.R_PLAN, reason)
        self.assertIn(self.sha_of("spec.md"), reason)

    def test_it_is_denied_even_when_nothing_is_blocked(self):
        self.place("spec.md", "spec_approved.md")
        decision = self.decision(self.pre_tool_use(overrides.OVERRIDES_FILE)[1])
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_a_project_may_switch_the_rule_off(self):
        self.write_config({"rules": {"overrides-are-human-only": "off"}})
        self.assertEqual(self.pre_tool_use(overrides.OVERRIDES_FILE), (0, ""))

    def test_an_override_file_outside_a_feature_is_not_the_override_file(self):
        # `.spark/overrides.jsonl` belongs to no feature; nothing claims it.
        target = self.write_artifact(".spark/overrides.jsonl", "{}\n")
        self.assertIsNone(rules.evaluate(self.root, target))


class TestCheckShowsOverrides(OverrideTestCase):
    def test_an_overridden_gate_is_reported_not_hidden(self):
        # An override is meant to be seen. `check` must not report a clean project
        # just because someone overruled a gate.
        import io
        from contextlib import redirect_stdout

        from aspark_guard import cli

        self.place("spec.md", "spec_draft.md")
        self.write_artifact(f".spark/{self.FEATURE}/plan.md", "| **Status** | `approved` |")
        self.grant(rules.R_PLAN, "spec.md", reason="planning ahead of legal sign-off")

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["check", str(self.root)])
        out = buffer.getvalue()

        self.assertIn("OVERRIDDEN", out)
        self.assertIn(rules.R_PLAN, out)
        self.assertIn("1 overridden", out)
        self.assertIn("0 would be blocked", out)


class TestParsing(OverrideTestCase):
    def test_malformed_lines_are_skipped(self):
        self.place("spec.md", "spec_draft.md")
        path = self.root / ".spark" / self.FEATURE / overrides.OVERRIDES_FILE
        path.write_text(
            "not json\n"
            "[]\n"
            '{"rule": 5}\n'
            '{"rule":"x"}\n'
            "\n",
            encoding="utf-8",
        )
        self.assertEqual(overrides.read(self.root, self.FEATURE), [])
        self.assertIsNotNone(rules.evaluate(self.root, self.target("plan.md")))

    def test_a_missing_file_covers_nothing(self):
        self.assertEqual(overrides.read(self.root, self.FEATURE), [])
        self.assertFalse(
            overrides.covers(self.root, self.FEATURE, rules.R_PLAN, "spec.md", "abc")
        )

    def test_an_unreadable_artifact_can_never_be_overridden(self):
        # No current hash means nothing to have been overruled.
        self.assertFalse(
            overrides.covers(self.root, self.FEATURE, rules.R_PLAN, "spec.md", None)
        )


if __name__ == "__main__":
    unittest.main()
