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


class TestWaitingAndEnded(ActivityTestCase):
    def test_a_permission_dialog_marks_the_session_waiting(self):
        code, out = self.hook("permission-request", "permission_request.json")

        self.assertEqual((code, out), (0, ""), "the guard never decides a permission")
        [entry] = self.activity_entries()
        self.assertEqual((entry["state"], entry["reason"]), ("waiting", "permission"))

    def test_the_tool_input_of_the_request_is_not_recorded(self):
        self.hook("permission-request", "permission_request.json")
        text = self.activity_file.read_text(encoding="utf-8")
        for marker in ("TOOL_COMMAND", "TOOL_DESCRIPTION", "Bash", "addRules"):
            self.assertNotIn(marker, text)

    def test_the_next_event_supersedes_waiting(self):
        self.hook("permission-request", "permission_request.json")
        self.hook("stop", "stop.json")
        states = [e["state"] for e in self.activity_entries()]
        self.assertEqual(states, ["waiting", "idle"])

    def test_session_end_records_the_allowlisted_reason(self):
        for reason in ("clear", "prompt_input_exit", "logout", "other"):
            with self.subTest(reason=reason):
                self.hook("session-end", "session_end.json", reason=reason)
                entry = self.activity_entries()[-1]
                self.assertEqual((entry["state"], entry["reason"]), ("ended", reason))

    def test_an_unknown_end_reason_is_recorded_as_other(self):
        for reason in ("resume", "SECRET_REASON", "", 7, None):
            with self.subTest(reason=reason):
                self.hook("session-end", "session_end.json", reason=reason)
                self.assertEqual(self.activity_entries()[-1]["reason"], "other")
        self.assertNotIn("SECRET_REASON", self.activity_file.read_text(encoding="utf-8"))

    def test_two_sessions_interleave_and_filter_cleanly(self):
        sequence = [
            ("user-prompt-submit", "user_prompt_submit.json", "s1"),
            ("user-prompt-submit", "user_prompt_submit.json", "s2"),
            ("permission-request", "permission_request.json", "s1"),
            ("stop", "stop.json", "s2"),
            ("stop", "stop.json", "s1"),
            ("session-end", "session_end.json", "s2"),
        ]
        for command, fixture, sid in sequence:
            self.hook(command, fixture, session_id=sid)

        by_session = {}
        for entry in self.activity_entries():
            by_session.setdefault(entry["session_id"], []).append(entry["state"])
        self.assertEqual(by_session["s1"], ["busy", "waiting", "idle"])
        self.assertEqual(by_session["s2"], ["busy", "idle", "ended"])

    def test_a_killed_session_gets_nothing_written_on_its_behalf(self):
        # s1 goes quiet without an end; s2 starts, works and ends.
        self.hook("user-prompt-submit", "user_prompt_submit.json", session_id="s1")
        for command, fixture in (("user-prompt-submit", "user_prompt_submit.json"),
                                 ("stop", "stop.json"), ("session-end", "session_end.json")):
            self.hook(command, fixture, session_id="s2")

        s1 = [e for e in self.activity_entries() if e["session_id"] == "s1"]
        self.assertEqual([e["state"] for e in s1], ["busy"], "its last line stays its last")
        states = {e["state"] for e in self.activity_entries()}
        self.assertNotIn("abandoned", states)


class TestSubagentStart(ActivityTestCase):
    def test_a_start_is_recorded_with_id_type_and_feature(self):
        spec = self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_approved.md")
        self.post_tool_use(spec, session_id="abc123")

        code, out = self.hook("subagent-start", "subagent_start.json")

        self.assertEqual((code, out), (0, ""))
        [entry] = self.activity_entries()
        self.assertEqual(entry["event"], "subagent_start")
        self.assertEqual(entry["agent_id"], "a26e028603b8b4f58")
        self.assertEqual(entry["agent_type"], "aspark:product-owner")
        self.assertEqual(entry["feature"], "weekly-stats")

    def test_the_feature_is_the_one_the_trail_would_infer(self):
        from aspark_guard import trail

        spec = self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_approved.md")
        self.post_tool_use(spec, session_id="abc123")
        self.hook("subagent-start", "subagent_start.json")
        self.assertEqual(self.activity_entries()[0]["feature"],
                         trail.feature_for_session(self.root, "abc123"))

    def test_the_feature_is_null_before_the_session_wrote_anything(self):
        self.hook("subagent-start", "subagent_start.json")
        self.assertIsNone(self.activity_entries()[0]["feature"])

    def test_a_harness_internal_agent_is_not_recorded(self):
        self.hook("subagent-start", "subagent_start.json", agent_type="")
        self.assertEqual(self.activity_entries(), [])

    def test_an_ended_session_leaves_an_open_start_as_it_is(self):
        self.hook("subagent-start", "subagent_start.json")
        self.hook("session-end", "session_end.json")
        events = [e["event"] for e in self.activity_entries()]
        self.assertEqual(events, ["subagent_start", "session_state"], "no synthetic finish")


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
