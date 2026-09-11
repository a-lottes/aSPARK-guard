"""The gate rules (M2): when a write is denied, and — just as important — when it is not."""

import unittest

from support import GuardTestCase, fixture_text
from aspark_guard import rules


class RuleTestCase(GuardTestCase):
    """A single feature under `.spark/weekly-stats/`."""

    FEATURE = "weekly-stats"

    def setUp(self):
        super().setUp()
        self.make_spark_project()

    def place(self, name: str, fixture: str):
        return self.write_fixture_artifact(f".spark/{self.FEATURE}/{name}", fixture)

    def target(self, name: str):
        return self.root / ".spark" / self.FEATURE / name

    def verdict(self, name: str, incoming: str | None = None):
        return rules.evaluate(self.root, self.target(name), incoming)


class TestPlanRequiresApprovedSpec(RuleTestCase):
    def test_blocks_a_plan_written_against_a_draft_spec(self):
        self.place("spec.md", "spec_draft.md")
        violation = self.verdict("plan.md")

        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, rules.R_PLAN)
        self.assertIn("`draft`", violation.state)
        message = violation.message()
        self.assertIn(rules.R_PLAN, message)
        self.assertIn("/story-time", message)
        self.assertIn("guard.json", message)

    def test_allows_a_plan_once_the_spec_is_approved(self):
        self.place("spec.md", "spec_approved.md")
        self.assertIsNone(self.verdict("plan.md"))

    def test_allows_when_there_is_no_spec_at_all(self):
        # Verified against `lean-rounds` in aSPARK's own repo: a real feature can
        # be missing an artifact entirely, and that is not this guard's business.
        self.assertIsNone(self.verdict("plan.md"))

    def test_allows_when_the_status_cannot_be_read(self):
        self.place("spec.md", "broken_header.md")
        self.assertIsNone(self.verdict("plan.md"))

        self.place("spec.md", "spec_template.md")
        self.assertIsNone(self.verdict("plan.md"))


class TestQaRequiresPassedReview(RuleTestCase):
    def test_blocks_qa_while_the_review_has_not_passed(self):
        self.place("review.md", "review_open.md")
        violation = self.verdict("qa.md")

        self.assertIsNotNone(violation)
        self.assertEqual(violation.rule_id, rules.R_QA)
        self.assertIn("`changes-requested`", violation.state)

    def test_allows_qa_once_the_review_passed(self):
        self.place("review.md", "review_passed.md")
        self.assertIsNone(self.verdict("qa.md"))

    def test_allows_qa_without_a_review_file(self):
        self.assertIsNone(self.verdict("qa.md"))


class TestReleaseRequiresGreenGates(RuleTestCase):
    def green(self):
        self.place("review.md", "review_passed.md")
        self.place("qa.md", "qa_passed.md")

    def test_allows_a_release_on_green_gates(self):
        self.green()
        self.assertIsNone(self.verdict("release.md"))

    def test_blocks_on_a_failed_review(self):
        self.place("review.md", "review_open.md")
        self.place("qa.md", "qa_passed.md")
        violation = self.verdict("release.md")
        self.assertEqual(violation.rule_id, rules.R_RELEASE)
        self.assertIn("review.md", violation.state)

    def test_blocks_on_failed_qa(self):
        self.place("review.md", "review_passed.md")
        self.place("qa.md", "qa_failed.md")
        violation = self.verdict("release.md")
        self.assertIn("`failed`", violation.state)

    def test_blocks_on_an_open_blocker_even_when_both_statuses_are_green(self):
        self.place("review.md", "review_passed.md")
        self.place("qa.md", "qa_passed_open_blocker.md")

        violation = self.verdict("release.md")
        self.assertIsNotNone(violation)
        self.assertIn("open Blocker", violation.state)
        self.assertIn("B1", violation.state)

    def test_names_every_red_gate_not_just_the_first(self):
        self.place("review.md", "review_open.md")
        self.place("qa.md", "qa_failed.md")
        state = self.verdict("release.md").state
        self.assertIn("review.md", state)
        self.assertIn("qa.md", state)

    def test_an_abort_record_is_allowed_over_red_gates(self):
        # Refusing this would block the very artifact that documents why nothing
        # shipped. A Write carries its content; an Edit does not.
        self.place("review.md", "review_open.md")
        self.place("qa.md", "qa_failed.md")

        self.assertIsNone(self.verdict("release.md", fixture_text("release_aborted.md")))

        self.place("release.md", "release_aborted.md")
        self.assertIsNone(self.verdict("release.md"))

    def test_a_non_abort_release_is_still_blocked_when_content_is_present(self):
        self.place("review.md", "review_open.md")
        self.assertIsNotNone(self.verdict("release.md", "| **Status** | `released` |"))


class TestNotGated(RuleTestCase):
    def test_spec_and_review_and_loose_notes_are_never_blocked(self):
        self.place("spec.md", "spec_draft.md")
        for name in ("spec.md", "review.md", "evidence.md", "notes.md"):
            with self.subTest(artifact=name):
                self.assertIsNone(self.verdict(name))

    def test_the_project_wide_constitution_is_never_blocked(self):
        self.write_artifact(".spark/constitution.md", "| **Status** | `active` |")
        self.assertIsNone(rules.evaluate(self.root, self.root / ".spark" / "constitution.md"))


class TestOpenBlockerParsing(unittest.TestCase):
    def test_exact_open_is_the_only_open_state(self):
        # The QA template says so literally: a suffixed or renamed value "silently
        # drops the finding from every open-findings view".
        self.assertEqual(
            rules.open_blockers(fixture_text("qa_passed_open_blocker.md")), ["B1"]
        )

    def test_real_world_severity_and_status_shapes_are_not_open(self):
        # Taken from aSPARK's own qa.md files: `Blocker → superseded` with a status
        # of `fixed r6, reconfirmed r8`.
        self.assertEqual(rules.open_blockers(fixture_text("qa_real_world_rows.md")), [])

    def test_a_file_without_a_findings_table_has_no_blockers(self):
        self.assertEqual(rules.open_blockers(fixture_text("qa_passed.md")), [])
        self.assertEqual(rules.open_blockers(""), [])

    def test_minor_findings_are_not_blockers(self):
        table = (
            "| # | Severity | Steps | Expected vs. observed | Status |\n"
            "|---|---|---|---|---|\n"
            "| B7 | Minor | x | y | open |\n"
        )
        self.assertEqual(rules.open_blockers(table), [])


if __name__ == "__main__":
    unittest.main()
