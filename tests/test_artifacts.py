"""Locating, classifying and reading `.spark/` artifacts."""

import unittest

from support import FIXTURES, GuardTestCase, fixture_text
from aspark_guard import artifacts


class TestParseStatus(unittest.TestCase):
    def test_reads_a_single_status_from_the_header_table(self):
        self.assertEqual(artifacts.parse_status(fixture_text("spec_approved.md")), "approved")
        self.assertEqual(artifacts.parse_status(fixture_text("spec_draft.md")), "draft")
        self.assertEqual(artifacts.parse_status(fixture_text("review_passed.md")), "passed")

    def test_an_uninstantiated_template_has_no_status(self):
        # The template row lists every option; picking one would invent a fact.
        self.assertIsNone(artifacts.parse_status(fixture_text("spec_template.md")))

    def test_an_annotated_status_reads_the_first_value(self):
        # Found by running the parser over aSPARK's own artifacts: a real
        # release.md annotates its status with further backticked values. Counting
        # them and giving up loses a status that is plainly stated.
        self.assertEqual(
            artifacts.parse_status(fixture_text("release_annotated.md")), "handed-off"
        )

    def test_choices_and_annotation_are_told_apart(self):
        self.assertIsNone(artifacts.parse_status(r"| **Status** | `a` \| `b` |"))
        self.assertEqual(artifacts.parse_status("| **Status** | `a` (see `b`) |"), "a")

    def test_missing_or_unparseable_header_yields_none(self):
        self.assertIsNone(artifacts.parse_status(fixture_text("broken_header.md")))
        self.assertIsNone(artifacts.parse_status(""))
        self.assertIsNone(artifacts.parse_status("| **Status** |"))

    def test_status_without_backticks_is_accepted(self):
        self.assertEqual(artifacts.parse_status("| **Status** | approved |"), "approved")


class TestLocating(GuardTestCase):
    def test_finds_the_root_from_a_nested_file_that_does_not_exist_yet(self):
        self.make_spark_project()
        unwritten = self.root / ".spark" / "f" / "plan.md"
        self.assertEqual(artifacts.find_spark_root(unwritten), self.root.resolve())

    def test_returns_none_without_a_spark_directory(self):
        self.assertIsNone(artifacts.find_spark_root(self.root / "src" / "app.py"))

    def test_classifies_spark_artifacts_and_excludes_the_guards_own_files(self):
        self.make_spark_project()
        spec = self.write_artifact(".spark/f/spec.md", "x")
        code = self.write_artifact("src/app.py", "x")
        own = self.write_artifact(".spark/.guard/ledger.jsonl", "{}")

        self.assertTrue(artifacts.is_spark_artifact(spec, self.root))
        self.assertFalse(artifacts.is_spark_artifact(code, self.root))
        self.assertFalse(artifacts.is_spark_artifact(own, self.root))
        self.assertTrue(artifacts.is_guard_own_file(own, self.root))

    def test_feature_comes_from_the_path(self):
        self.make_spark_project()
        self.assertEqual(
            artifacts.feature_of(self.root / ".spark/weekly-stats/spec.md", self.root),
            "weekly-stats",
        )
        # The constitution is project-wide, so it has no feature.
        self.assertIsNone(artifacts.feature_of(self.root / ".spark/constitution.md", self.root))

    def test_iter_artifacts_is_sorted_and_skips_the_guard_dir(self):
        self.make_spark_project()
        self.write_artifact(".spark/b/spec.md", "x")
        self.write_artifact(".spark/a/spec.md", "x")
        self.write_artifact(".spark/.guard/ledger.jsonl", "{}")

        found = [artifacts.relative_to_root(p, self.root) for p in artifacts.iter_artifacts(self.root)]
        self.assertEqual(found, [".spark/a/spec.md", ".spark/b/spec.md"])


class TestHashing(GuardTestCase):
    def test_hash_changes_with_content_and_is_none_for_a_missing_file(self):
        path = self.write_artifact("a.md", "one")
        first = artifacts.sha256_file(path)
        path.write_text("two", encoding="utf-8")
        self.assertNotEqual(first, artifacts.sha256_file(path))
        self.assertIsNone(artifacts.sha256_file(self.root / "nope.md"))


class TestFixturesExist(unittest.TestCase):
    def test_every_fixture_referenced_here_is_present(self):
        for name in ("spec_approved.md", "spec_draft.md", "spec_template.md",
                     "broken_header.md", "review_passed.md", "release_annotated.md"):
            self.assertTrue((FIXTURES / "artifacts" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
