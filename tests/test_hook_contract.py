"""Contract tests against recorded hook payloads.

These use the payload shapes documented for Claude Code hooks, with the repo path
substituted in. They exist so that a change to the hook API surfaces here rather
than as a plugin that silently stops working in a real session — and they run
without Claude Code.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from support import FIXTURES, REPO_ROOT, GuardTestCase

PAYLOADS = FIXTURES / "payloads"


def payload(name: str, root: Path) -> dict:
    raw = (PAYLOADS / name).read_text(encoding="utf-8").replace("__ROOT__", str(root))
    return json.loads(raw)


class TestRecordedPayloads(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.make_spark_project()

    def test_pre_tool_use_allows_silently_until_m2(self):
        self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_draft.md")
        self.write_artifact(".spark/weekly-stats/plan.md", "# Plan\n")

        code, out = self.run_hook("pre-tool-use", payload("pre_tool_use_write.json", self.root))

        # M2 will deny this exact payload — a plan written against a draft spec.
        self.assertEqual(code, 0)
        self.assertEqual(out, "")

    def test_post_tool_use_records_an_edit(self):
        self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_approved.md")

        code, out = self.run_hook("post-tool-use", payload("post_tool_use_edit.json", self.root))

        self.assertEqual((code, out), (0, ""))
        entry = self.ledger_entries()[0]
        self.assertEqual(entry["path"], ".spark/weekly-stats/spec.md")
        self.assertEqual(entry["agent_type"], "product-owner")

    def test_subagent_stop_is_inert_until_m4(self):
        code, out = self.run_hook("subagent-stop", payload("subagent_stop.json", self.root))
        self.assertEqual((code, out), (0, ""))

    def test_session_start_is_quiet_with_nothing_to_report(self):
        code, out = self.run_hook("session-start", payload("session_start.json", self.root))
        self.assertEqual((code, out), (0, ""))

    def test_stdout_stays_empty_or_is_plain_text_never_stray_json(self):
        # PreToolUse is the only event where stdout JSON carries meaning. Until M2
        # emits a decision, nothing may print JSON that the harness would parse.
        for name, command in (
            ("pre_tool_use_write.json", "pre-tool-use"),
            ("post_tool_use_edit.json", "post-tool-use"),
            ("subagent_stop.json", "subagent-stop"),
        ):
            with self.subTest(event=command):
                _, out = self.run_hook(command, payload(name, self.root))
                self.assertFalse(out.strip().startswith("{"), out)


class TestEntryPoint(GuardTestCase):
    """The real `bin/guard.py`, in a real subprocess, the way the harness runs it."""

    def test_it_runs_as_a_script_and_records(self):
        self.make_spark_project()
        self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_approved.md")
        event = payload("post_tool_use_edit.json", self.root)

        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "guard.py"), "post-tool-use"],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(self.ledger_entries()), 1)

    def test_scan_reports_without_changing_anything(self):
        self.make_spark_project()
        self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_approved.md")
        before = self.tree()

        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "guard.py"), "scan", str(self.root)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("artifacts:       1", result.stdout)
        self.assertEqual(self.tree(), before)


if __name__ == "__main__":
    unittest.main()
