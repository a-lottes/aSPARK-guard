"""The hash ledger: what gets recorded, and what deliberately does not."""

import unittest

from support import GuardTestCase


class TestRecording(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.make_spark_project()

    def test_a_write_produces_one_entry_with_hash_status_and_feature(self):
        target = self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_approved.md")
        self.post_tool_use(target, agent_type="product-owner")

        entries = self.ledger_entries()
        self.assertEqual(len(entries), 1)

        entry = entries[0]
        self.assertEqual(entry["event"], "artifact_write")
        self.assertEqual(entry["path"], ".spark/weekly-stats/spec.md")
        self.assertEqual(entry["feature"], "weekly-stats")
        self.assertEqual(entry["status"], "approved")
        self.assertEqual(entry["agent_type"], "product-owner")
        self.assertEqual(entry["session_id"], "test-session")
        self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(entry["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_successive_changes_form_a_chain(self):
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_draft.md")
        self.post_tool_use(target)

        approved = target.read_text(encoding="utf-8").replace("`draft`", "`approved`")
        target.write_text(approved, encoding="utf-8")
        self.post_tool_use(target)

        entries = self.ledger_entries()
        self.assertEqual([e["status"] for e in entries], ["draft", "approved"])
        self.assertNotEqual(entries[0]["sha256"], entries[1]["sha256"])

    def test_an_unchanged_file_is_not_recorded_twice(self):
        # A no-op Edit, or a write the tool ultimately failed to make, must not
        # leave a second entry claiming something happened.
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_approved.md")
        self.post_tool_use(target)
        self.post_tool_use(target)
        self.assertEqual(len(self.ledger_entries()), 1)

    def test_writes_outside_spark_are_ignored(self):
        target = self.write_artifact("src/app.py", "print('hi')\n")
        self.post_tool_use(target)
        self.assertFalse(self.ledger_file.exists())

    def test_the_guards_own_files_are_not_recorded(self):
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_approved.md")
        self.post_tool_use(target)
        self.post_tool_use(self.ledger_file)
        self.assertEqual(len(self.ledger_entries()), 1)

    def test_non_markdown_artifacts_are_recorded_without_a_status(self):
        # overrides.jsonl must be in the chain too — that is the point of it.
        target = self.write_artifact(".spark/f/overrides.jsonl", '{"rule":"x"}\n')
        self.post_tool_use(target)

        entry = self.ledger_entries()[0]
        self.assertEqual(entry["path"], ".spark/f/overrides.jsonl")
        self.assertIsNone(entry["status"])

    def test_a_template_status_is_recorded_as_unknown_not_guessed(self):
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_template.md")
        self.post_tool_use(target)
        self.assertIsNone(self.ledger_entries()[0]["status"])

    def test_a_deleted_file_produces_no_entry(self):
        target = self.root / ".spark" / "f" / "gone.md"
        self.post_tool_use(target)
        self.assertFalse(self.ledger_file.exists())


class TestLedgerReading(GuardTestCase):
    def test_corrupt_lines_are_skipped_not_fatal(self):
        self.make_spark_project()
        self.write_artifact(
            ".spark/.guard/ledger.jsonl",
            '{"path":"a","sha256":"1"}\nnot json at all\n\n{"path":"b","sha256":"2"}\n',
        )
        from aspark_guard import ledger

        self.assertEqual(len(list(ledger.read_entries(self.root))), 2)
        self.assertEqual(ledger.last_hash_by_path(self.root), {"a": "1", "b": "2"})


if __name__ == "__main__":
    unittest.main()
