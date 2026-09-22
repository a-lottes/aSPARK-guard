"""The live activity log (activity-trail): session state and subagent runs."""

import json
import re
import unittest
from pathlib import Path

from support import FIXTURES, GuardTestCase

PAYLOADS = FIXTURES / "payloads"

TS_MS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def payload(name: str, root: Path, **extra) -> dict:
    """A payload recorded in the T1 hook spike, with this test's repo substituted in."""
    raw = (PAYLOADS / name).read_text(encoding="utf-8").replace("__ROOT__", str(root))
    data = json.loads(raw)
    data.update(extra)
    return data


class ActivityTestCase(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.make_spark_project()

    @property
    def activity_file(self) -> Path:
        return self.root / ".spark" / ".guard" / "activity.jsonl"

    def activity_entries(self) -> list[dict]:
        if not self.activity_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.activity_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def hook(self, command: str, fixture: str, **extra) -> tuple[int, str]:
        return self.run_hook(command, payload(fixture, self.root, **extra))


class TestSessionState(ActivityTestCase):
    def test_a_prompt_marks_the_session_busy(self):
        code, out = self.hook("user-prompt-submit", "user_prompt_submit.json")

        self.assertEqual((code, out), (0, ""))
        [entry] = self.activity_entries()
        self.assertEqual(entry["event"], "session_state")
        self.assertEqual((entry["state"], entry["reason"]), ("busy", "prompt"))
        self.assertEqual(entry["session_id"], "abc123")

    def test_a_finished_turn_marks_the_session_idle(self):
        code, out = self.hook("stop", "stop.json")

        self.assertEqual((code, out), (0, ""))
        [entry] = self.activity_entries()
        self.assertEqual((entry["state"], entry["reason"]), ("idle", "stop"))

    def test_every_line_carries_version_timestamp_event_and_session(self):
        self.hook("user-prompt-submit", "user_prompt_submit.json")
        self.hook("stop", "stop.json")

        for entry in self.activity_entries():
            with self.subTest(entry=entry):
                self.assertEqual(entry["v"], 1)
                self.assertRegex(entry["ts"], TS_MS)
                self.assertIn("event", entry)
                self.assertIn("session_id", entry)

    def test_lines_are_written_in_the_ledgers_sorted_key_form(self):
        self.hook("user-prompt-submit", "user_prompt_submit.json")
        line = self.activity_file.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(line, json.dumps(json.loads(line), ensure_ascii=False, sort_keys=True))

    def test_a_missing_session_id_is_recorded_as_null(self):
        data = payload("stop.json", self.root)
        del data["session_id"]
        self.run_hook("stop", data)
        [entry] = self.activity_entries()
        self.assertIsNone(entry["session_id"])


class TestSwitch(ActivityTestCase):
    def test_activity_false_writes_nothing(self):
        self.write_config({"activity": False})
        self.hook("user-prompt-submit", "user_prompt_submit.json")
        self.hook("stop", "stop.json")
        self.assertFalse(self.activity_file.exists())

    def test_enabled_false_switches_activity_off_too(self):
        self.write_config({"enabled": False})
        self.hook("user-prompt-submit", "user_prompt_submit.json")
        self.assertFalse(self.activity_file.exists())

    def test_activity_is_on_by_default(self):
        self.hook("stop", "stop.json")
        self.assertTrue(self.activity_file.exists())


if __name__ == "__main__":
    unittest.main()
