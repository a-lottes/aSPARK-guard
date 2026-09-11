"""The template contract check (M4): drift, not completeness — and never a block."""

import json
import unittest

from support import GuardTestCase
from aspark_guard import templates


class TestSpec(unittest.TestCase):
    def check(self, text):
        return templates.check_text(templates.SPEC, text)

    def test_a_well_formed_story_and_criterion_pass(self):
        self.assertEqual(
            self.check(
                "### US-1 (Must): A title\n\n"
                "- [ ] AC-1.1: Given a thing, when it happens, then something.\n"
                "- [x] AC-1.2: Another one.\n"
            ),
            [],
        )

    def test_a_suffixed_criterion_id_is_reported(self):
        # Found in aSPARK's own situational-lenses spec. aspark-graph's
        # _AC_RE requires `AC-<n>.<m>` immediately before the colon, so
        # `AC-2.1a:` matches nothing and the criterion is invisible to it.
        findings = self.check("- [ ] AC-2.1a: Given a Review-owned lens, then …\n")
        self.assertEqual(len(findings), 1)
        self.assertIn("aspark-graph will not see it", findings[0])

    def test_a_malformed_story_heading_is_reported(self):
        self.assertEqual(len(self.check("### US-1: no MoSCoW here\n")), 1)
        self.assertEqual(len(self.check("### US-one (Must): not a number\n")), 1)

    def test_prose_mentioning_an_id_is_not_a_criterion(self):
        # Real specs discuss AC-2.1a in tables and sentences constantly.
        self.assertEqual(
            self.check(
                "| C1 | Folded into §1, AC-2.1a and AC-3.4. |\n"
                "Some prose about US-1 (Must) and AC-1.1 in passing.\n"
            ),
            [],
        )

    def test_an_empty_or_new_spec_says_nothing(self):
        # Drift, not completeness: a spec with no stories yet is not malformed.
        self.assertEqual(self.check(""), [])
        self.assertEqual(self.check("# Spec: weekly-stats\n\n## 1. Problem & Goal\n"), [])


class TestPlan(unittest.TestCase):
    HEADER = "| # | Task | Story | Covers (AC / NFR) | Depends on | Status | Definition of Done |"

    def check(self, text):
        return templates.check_text(templates.PLAN, text)

    def test_the_real_header_with_two_extra_columns_passes(self):
        # The constitution: appending a column is allowed, the consumer matches
        # headings by substring.
        self.assertEqual(
            self.check(f"## 3. Task Breakdown\n\n{self.HEADER}\n|---|---|---|---|---|---|---|\n"),
            [],
        )

    def test_a_missing_protected_column_is_reported(self):
        findings = self.check(
            "## 3. Task Breakdown\n\n| # | Task | Story | Status |\n|---|---|---|---|\n"
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("Definition of Done", findings[0])

    def test_a_malformed_task_id_is_reported(self):
        findings = self.check(
            f"## 3. Task Breakdown\n\n{self.HEADER}\n|---|---|---|---|---|---|---|\n"
            "| T1 | fine | US-1 | | | `done` | ok |\n"
            "| T2b | suffixed | US-1 | | | `done` | ok |\n"
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("T2b", findings[0])

    def test_a_heading_without_a_table_yet_says_nothing(self):
        self.assertEqual(self.check("## 3. Task Breakdown\n\nComing next round.\n"), [])

    def test_a_plan_that_mentions_the_section_in_prose_is_not_the_section(self):
        # The Handoff block says "see §3 Task Breakdown"; that is not a heading.
        self.assertEqual(self.check("- **Open:** see §3 Task Breakdown for which\n"), [])


class TestReview(unittest.TestCase):
    def check(self, text):
        return templates.check_text(templates.REVIEW, text)

    def test_the_real_findings_table_passes(self):
        self.assertEqual(
            self.check(
                "## 3. Findings\n\n| # | Severity | Location | Finding | Status |\n"
                "|---|---|---|---|---|\n| F1 | Minor | a.py:1 | x | fixed r1 |\n"
            ),
            [],
        )

    def test_a_missing_column_and_a_bad_id_are_reported(self):
        findings = self.check(
            "## 3. Findings\n\n| # | Severity | Finding | Status |\n|---|---|---|---|\n"
            "| F1a | Minor | x | open |\n"
        )
        self.assertEqual(len(findings), 2)
        self.assertTrue(any("Location" in f for f in findings))
        self.assertTrue(any("F1a" in f for f in findings))


class TestQaAndRelease(unittest.TestCase):
    def test_a_verification_table_needs_result_alongside_spec_id(self):
        ok = "| Spec ID | Steps performed | Expected | Observed | Result |\n|---|---|---|---|---|\n"
        self.assertEqual(templates.check_text(templates.QA, ok), [])

        bad = "| Spec ID | Steps performed | Expected | Observed | Verdict |\n|---|---|---|---|---|\n"
        findings = templates.check_text(templates.QA, bad)
        self.assertEqual(len(findings), 1)
        self.assertIn("Result", findings[0])

    def test_the_release_header_needs_status_and_version(self):
        ok = "| | |\n|---|---|\n| **Status** | `released` |\n| **Version** | v1.0.0 |\n"
        self.assertEqual(templates.check_text(templates.RELEASE, ok), [])

        findings = templates.check_text(
            templates.RELEASE, "| | |\n|---|---|\n| **Status** | `released` |\n"
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("Version", findings[0])

    def test_a_release_with_no_header_table_yet_says_nothing(self):
        self.assertEqual(templates.check_text(templates.RELEASE, "# Release: x\n"), [])

    def test_an_unknown_artifact_is_never_checked(self):
        self.assertEqual(templates.check_text("evidence.md", "anything at all"), [])


class TestThroughTheHook(GuardTestCase):
    FEATURE = "weekly-stats"

    def setUp(self):
        super().setUp()
        self.make_spark_project()

    def test_drift_is_reported_as_context_and_never_denies(self):
        target = self.write_artifact(
            f".spark/{self.FEATURE}/spec.md",
            "| **Status** | `approved` |\n\n- [ ] AC-2.1a: Given a thing, then something.\n",
        )
        code, out = self.post_tool_use(target)

        self.assertEqual(code, 0)
        specific = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PostToolUse")
        self.assertNotIn("permissionDecision", specific,
                         "PostToolUse must never carry a decision")
        self.assertIn("AC-2.1a", specific["additionalContext"])
        self.assertIn("no version handshake", specific["additionalContext"])

    def test_a_clean_artifact_produces_no_output(self):
        target = self.write_fixture_artifact(f".spark/{self.FEATURE}/spec.md", "spec_approved.md")
        self.assertEqual(self.post_tool_use(target), (0, ""))

    def test_the_check_can_be_switched_off(self):
        self.write_config({"template_check": False})
        target = self.write_artifact(
            f".spark/{self.FEATURE}/spec.md", "- [ ] AC-2.1a: bad\n"
        )
        self.assertEqual(self.post_tool_use(target), (0, ""))

    def test_the_write_is_still_recorded_even_when_it_drifts(self):
        target = self.write_artifact(
            f".spark/{self.FEATURE}/spec.md", "- [ ] AC-2.1a: bad\n"
        )
        self.post_tool_use(target)
        self.assertEqual(len(self.ledger_entries()), 1)


if __name__ == "__main__":
    unittest.main()
