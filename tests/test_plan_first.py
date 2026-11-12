"""R5, code-requires-approved-plan: a write outside `.spark/` waits for the plan.

Three layers, as CONTRIBUTING asks: the rule against artifact states, the hook with a
recorded payload, and the inputs that must never turn into a block.
"""

import json
import unittest
from pathlib import Path

from support import FIXTURES, GuardTestCase, fixture_text

from aspark_guard import rules

FEATURE = "weekly-stats"
SESSION = "abc123"


def plan(status: str) -> str:
    return f"# Plan: x\n\n| | |\n|---|---|\n| **Status** | `{status}` |\n"


def payload(root: Path, **changes) -> dict:
    raw = (FIXTURES / "payloads" / "pre_tool_use_code_write.json").read_text(encoding="utf-8")
    event = json.loads(raw.replace("__ROOT__", str(root)))
    event.update(changes)
    return event


class PlanFirstTestCase(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.make_spark_project()
        self.code = self.write_artifact("src/app.py", "a\n")

    def session_writes(self, name: str, content: str, feature: str = FEATURE,
                       session: str = SESSION) -> Path:
        """An artifact write the way a session makes it: the file, then the ledger line."""
        path = self.write_artifact(f".spark/{feature}/{name}", content)
        self.post_tool_use(path, session_id=session)
        return path

    def code_write(self, **changes):
        return self.run_hook("pre-tool-use", payload(self.root, **changes))

    def assertDenied(self, result, *needles):
        code, out = result
        self.assertEqual(code, 0)
        specific = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(specific["permissionDecision"], "deny")
        for needle in needles:
            self.assertIn(needle, specific["permissionDecisionReason"])


class TestSessionScope(PlanFirstTestCase):
    def test_a_session_that_wrote_no_trail_is_never_held(self):
        self.write_fixture_artifact(f".spark/{FEATURE}/spec.md", "spec_draft.md")
        self.assertEqual(self.code_write(), (0, ""))

    def test_code_is_denied_after_this_session_wrote_a_spec_without_a_plan(self):
        self.session_writes("spec.md", fixture_text("spec_approved.md"))
        self.assertDenied(self.code_write(), rules.R_CODE, "has no plan.md", "/sprint-plan",
                          "guard.json")

    def test_code_is_denied_while_the_plan_is_a_draft(self):
        self.session_writes("spec.md", fixture_text("spec_approved.md"))
        self.session_writes("plan.md", plan("draft"))
        self.assertDenied(self.code_write(), "`draft`, not `approved`")

    def test_code_is_allowed_once_the_plan_is_approved(self):
        self.session_writes("spec.md", fixture_text("spec_approved.md"))
        self.session_writes("plan.md", plan("draft"))
        self.session_writes("plan.md", plan("approved"))
        self.assertEqual(self.code_write(), (0, ""))

    def test_another_sessions_trail_does_not_hold_this_one(self):
        self.session_writes("spec.md", fixture_text("spec_draft.md"), session="someone-else")
        self.assertEqual(self.code_write(), (0, ""))

    def test_drafting_the_next_feature_while_building_an_approved_one_is_allowed(self):
        self.session_writes("spec.md", fixture_text("spec_approved.md"))
        self.session_writes("plan.md", plan("approved"))
        self.session_writes("spec.md", fixture_text("spec_draft.md"), feature="next-one")
        self.assertEqual(self.code_write(), (0, ""))

    def test_a_feature_past_planning_is_never_held(self):
        self.session_writes("spec.md", fixture_text("spec_approved.md"))
        self.write_fixture_artifact(f".spark/{FEATURE}/review.md", "review_open.md")
        self.assertEqual(self.code_write(), (0, ""))

    def test_an_unreadable_plan_status_does_not_block(self):
        self.session_writes("spec.md", fixture_text("spec_approved.md"))
        self.session_writes("plan.md", "# Plan with no header table\n")
        self.assertEqual(self.code_write(), (0, ""))

    def test_writes_under_dot_spark_are_left_to_the_other_rules(self):
        self.session_writes("spec.md", fixture_text("spec_approved.md"))
        target = self.root / ".spark" / FEATURE / "notes.md"
        event = payload(self.root, tool_input={"file_path": str(target)})
        self.assertEqual(self.run_hook("pre-tool-use", event), (0, ""))

    def test_a_file_outside_the_repo_is_untouched(self):
        self.session_writes("spec.md", fixture_text("spec_approved.md"))
        event = payload(self.root, tool_input={"file_path": "/tmp/elsewhere.py"})
        self.assertEqual(self.run_hook("pre-tool-use", event), (0, ""))


class TestModesAndConfig(PlanFirstTestCase):
    def setUp(self):
        super().setUp()
        self.session_writes("spec.md", fixture_text("spec_approved.md"))

    def test_off_switches_the_rule_off(self):
        self.write_config({"rules": {rules.R_CODE: "off"}})
        self.assertEqual(self.code_write(), (0, ""))

    def test_warn_allows_and_explains(self):
        self.write_config({"rules": {rules.R_CODE: "warn"}})
        code, out = self.code_write()
        specific = json.loads(out)["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", specific)
        self.assertIn(rules.R_CODE, specific["additionalContext"])

    def test_disabling_the_guard_disables_the_rule(self):
        self.write_config({"enabled": False})
        self.assertEqual(self.code_write(), (0, ""))

    def test_exempt_patterns_are_not_held(self):
        self.write_config({"plan_first_exempt": ["docs/*", "*.md"]})
        for rel in ("docs/guide.txt", "README.md"):
            event = payload(self.root, tool_input={"file_path": str(self.root / rel)})
            with self.subTest(rel=rel):
                self.assertEqual(self.run_hook("pre-tool-use", event), (0, ""))
        self.assertDenied(self.code_write(), rules.R_CODE)

    def test_without_a_ledger_the_session_scope_has_no_facts_and_stays_out(self):
        self.ledger_file.unlink()
        self.assertEqual(self.code_write(), (0, ""))

    def test_a_human_override_settles_the_block(self):
        _, out = self.code_write()
        reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
        line = next(l.strip() for l in reason.splitlines() if l.strip().startswith("{"))
        entry = json.loads(line)
        entry["reason"] = "hotfix agreed with the team"
        self.write_artifact(f".spark/{FEATURE}/overrides.jsonl", json.dumps(entry) + "\n")
        self.assertEqual(self.code_write(), (0, ""))


class TestAlwaysScope(PlanFirstTestCase):
    def setUp(self):
        super().setUp()
        self.write_config({"plan_first_scope": "always"})

    def test_code_before_any_spec_is_denied(self):
        self.assertDenied(self.code_write(), rules.R_CODE, "only under an approved plan")

    def test_an_approved_unreleased_plan_anywhere_allows_code(self):
        self.write_artifact(f".spark/{FEATURE}/plan.md", plan("approved"))
        self.assertEqual(self.code_write(session_id="any"), (0, ""))

    def test_a_released_feature_does_not_cover_new_code(self):
        self.write_artifact(f".spark/{FEATURE}/plan.md", plan("approved"))
        self.write_fixture_artifact(f".spark/{FEATURE}/release.md", "release_annotated.md")
        self.assertDenied(self.code_write(), rules.R_CODE)

    def test_an_unreadable_plan_keeps_the_guard_out_of_the_way(self):
        self.write_artifact(f".spark/{FEATURE}/plan.md", "# no header\n")
        self.assertEqual(self.code_write(), (0, ""))

    def test_an_unknown_scope_falls_back_to_session(self):
        self.write_config({"plan_first_scope": "everything"})
        self.assertEqual(self.code_write(), (0, ""))


class TestSilenceAndFailOpen(GuardTestCase):
    def test_no_dot_spark_means_no_output_and_no_files(self):
        target = self.write_artifact("src/app.py", "a\n")
        before = self.tree()
        event = payload(self.root, tool_input={"file_path": str(target)})
        self.assertEqual(self.run_hook("pre-tool-use", event), (0, ""))
        self.assertEqual(self.tree(), before)

    def test_hostile_session_ids_and_ledger_lines_never_block(self):
        self.make_spark_project()
        self.write_artifact("src/app.py", "a\n")
        self.write_artifact(".spark/.guard/ledger.jsonl",
                            'not json\n[]\n{"session_id": 7, "feature": 3, "path": null}\n')
        for session in (None, 7, ["x"], {}, ""):
            with self.subTest(session=session):
                event = payload(self.root, session_id=session)
                self.assertEqual(self.run_hook("pre-tool-use", event), (0, ""))

    def test_a_denied_code_write_creates_no_file(self):
        self.make_spark_project()
        self.write_artifact("src/app.py", "a\n")
        self.write_config({"plan_first_scope": "always"})
        before = self.tree()
        self.run_hook("pre-tool-use", payload(self.root))
        self.assertEqual(self.tree(), before)


if __name__ == "__main__":
    unittest.main()
