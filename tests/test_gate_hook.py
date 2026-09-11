"""The PreToolUse hook around the rules: decision payloads and the three modes."""

import json
import unittest

from support import GuardTestCase


class GateHookTestCase(GuardTestCase):
    FEATURE = "weekly-stats"

    def setUp(self):
        super().setUp()
        self.make_spark_project()
        self.write_fixture_artifact(f".spark/{self.FEATURE}/spec.md", "spec_draft.md")

    def pre_tool_use(self, name: str, content: str | None = None):
        tool_input = {"file_path": str(self.root / ".spark" / self.FEATURE / name)}
        if content is not None:
            tool_input["content"] = content
        return self.run_hook("pre-tool-use", {
            "session_id": "test-session",
            "cwd": str(self.root),
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": tool_input,
        })


class TestDecisionPayload(GateHookTestCase):
    def test_a_violation_denies_with_a_readable_reason(self):
        code, out = self.pre_tool_use("plan.md")

        self.assertEqual(code, 0, "the decision travels in the JSON, not the exit code")
        payload = json.loads(out)
        specific = payload["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PreToolUse")
        self.assertEqual(specific["permissionDecision"], "deny")

        reason = specific["permissionDecisionReason"]
        # Invariant 4: name the rule, the state that triggered it, and the way out.
        self.assertIn("plan-requires-approved-spec", reason)
        self.assertIn("`draft`", reason)
        self.assertIn("/story-time", reason)
        self.assertIn("guard.json", reason)

    def test_a_clean_write_produces_no_output_at_all(self):
        self.write_fixture_artifact(f".spark/{self.FEATURE}/spec.md", "spec_approved.md")
        self.assertEqual(self.pre_tool_use("plan.md"), (0, ""))

    def test_writes_outside_a_feature_are_untouched(self):
        target = self.write_artifact("src/app.py", "x")
        code, out = self.run_hook("pre-tool-use", {
            "cwd": str(self.root),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        })
        self.assertEqual((code, out), (0, ""))


class TestModes(GateHookTestCase):
    def test_warn_allows_but_says_so(self):
        self.write_config({"rules": {"plan-requires-approved-spec": "warn"}})
        code, out = self.pre_tool_use("plan.md")

        payload = json.loads(out)["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", payload,
                         "warn must not deny — it only adds context")
        self.assertIn("plan-requires-approved-spec", payload["additionalContext"])
        self.assertEqual(code, 0)

    def test_off_is_completely_silent(self):
        self.write_config({"rules": {"plan-requires-approved-spec": "off"}})
        self.assertEqual(self.pre_tool_use("plan.md"), (0, ""))

    def test_disabling_the_plugin_disables_the_rules(self):
        self.write_config({"enabled": False})
        self.assertEqual(self.pre_tool_use("plan.md"), (0, ""))

    def test_an_unknown_mode_falls_back_to_the_default(self):
        # "blocc" is not a mode; the config loader drops it and the default stands.
        self.write_config({"rules": {"plan-requires-approved-spec": "blocc"}})
        _, out = self.pre_tool_use("plan.md")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_each_rule_is_configured_independently(self):
        self.write_config({"rules": {"plan-requires-approved-spec": "off"}})
        self.write_fixture_artifact(f".spark/{self.FEATURE}/review.md", "review_open.md")

        self.assertEqual(self.pre_tool_use("plan.md"), (0, ""))
        _, out = self.pre_tool_use("qa.md")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")


class TestAbortPath(GateHookTestCase):
    def test_an_abort_release_passes_through_the_hook(self):
        self.write_fixture_artifact(f".spark/{self.FEATURE}/review.md", "review_open.md")
        self.write_fixture_artifact(f".spark/{self.FEATURE}/qa.md", "qa_failed.md")

        blocked = self.pre_tool_use("release.md", "| **Status** | `released` |")
        self.assertIn("deny", blocked[1])

        allowed = self.pre_tool_use("release.md", "| **Status** | `aborted` |")
        self.assertEqual(allowed, (0, ""))


class TestStillFailsOpen(GateHookTestCase):
    def test_hostile_input_never_denies(self):
        for raw in ("", "not json", "null", '{"tool_input": 5}',
                    '{"tool_input": {"file_path": 5}}'):
            with self.subTest(raw=raw):
                code, out = self.run_hook("pre-tool-use", raw)
                self.assertEqual(code, 0)
                self.assertEqual(out, "")

    def test_an_unreadable_prerequisite_never_denies(self):
        self.write_fixture_artifact(f".spark/{self.FEATURE}/spec.md", "broken_header.md")
        self.assertEqual(self.pre_tool_use("plan.md"), (0, ""))


if __name__ == "__main__":
    unittest.main()
