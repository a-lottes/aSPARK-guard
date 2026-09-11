"""Detecting artifacts edited outside the loop."""

import unittest

from support import GuardTestCase
from aspark_guard import drift


class TestDrift(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.make_spark_project()

    def test_an_empty_ledger_reports_nothing(self):
        self.write_fixture_artifact(".spark/f/spec.md", "spec_approved.md")
        self.assertEqual(drift.find_drifted(self.root), [])
        code, out = self.session_start()
        self.assertEqual((code, out), (0, ""))

    def test_a_file_the_ledger_never_saw_is_not_drift(self):
        # Artifacts that predate the install are the normal case on adoption.
        recorded = self.write_fixture_artifact(".spark/f/spec.md", "spec_approved.md")
        self.post_tool_use(recorded)
        self.write_fixture_artifact(".spark/f/review.md", "review_passed.md")

        self.assertEqual(drift.find_drifted(self.root), [])
        self.assertEqual(self.session_start()[1], "")

    def test_an_edit_outside_the_loop_is_reported(self):
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_draft.md")
        self.post_tool_use(target)

        # The human opens an editor; no hook ever fires.
        target.write_text(target.read_text(encoding="utf-8").replace("`draft`", "`approved`"),
                          encoding="utf-8")

        self.assertEqual(drift.find_drifted(self.root), [".spark/f/spec.md"])

        code, out = self.session_start()
        self.assertEqual(code, 0)
        self.assertIn(".spark/f/spec.md", out)
        self.assertIn("outside the loop", out)
        self.assertIn("unverified", out)

    def test_a_recorded_write_clears_the_drift(self):
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_draft.md")
        self.post_tool_use(target)
        target.write_text("changed", encoding="utf-8")
        self.assertTrue(drift.find_drifted(self.root))

        self.post_tool_use(target)
        self.assertEqual(drift.find_drifted(self.root), [])

    def test_drift_check_can_be_switched_off(self):
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_draft.md")
        self.post_tool_use(target)
        target.write_text("changed", encoding="utf-8")
        self.write_config({"drift_check": False})

        self.assertEqual(self.session_start()[1], "")


class TestNotice(unittest.TestCase):
    def test_empty_input_produces_no_text(self):
        self.assertEqual(drift.format_notice([]), "")

    def test_singular_and_plural_read_correctly(self):
        self.assertIn("1 .spark artifact changed", drift.format_notice([".spark/a.md"]))
        self.assertIn("2 .spark artifacts changed",
                      drift.format_notice([".spark/a.md", ".spark/b.md"]))

    def test_a_long_list_is_truncated(self):
        paths = [f".spark/f/{i}.md" for i in range(25)]
        notice = drift.format_notice(paths)
        self.assertIn("25 .spark artifacts changed", notice)
        self.assertIn("… and 15 more", notice)
        self.assertNotIn(".spark/f/20.md", notice)


if __name__ == "__main__":
    unittest.main()
