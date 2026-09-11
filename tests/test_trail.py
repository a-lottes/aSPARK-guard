"""The agent-run trail (M4)."""

import unittest

from support import GuardTestCase


class TrailTestCase(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.make_spark_project()

    def subagent_stop(self, agent_type="reviewer", **extra):
        payload = {
            "session_id": "test-session",
            "cwd": str(self.root),
            "hook_event_name": "SubagentStop",
            "agent_id": "sub-1",
            "agent_type": agent_type,
            "last_assistant_message": "Review complete. Found three issues in auth.py.",
            "stop_reason": "end_turn",
        }
        payload.update(extra)
        return self.run_hook("subagent-stop", payload)

    @property
    def trail_file(self):
        return self.root / ".spark" / ".guard" / "trail.jsonl"

    def trail_entries(self):
        import json

        if not self.trail_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.trail_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


class TestRecording(TrailTestCase):
    def test_a_finished_subagent_produces_one_line(self):
        code, out = self.subagent_stop()

        self.assertEqual((code, out), (0, ""), "the trail is silent, it only writes")
        entries = self.trail_entries()
        self.assertEqual(len(entries), 1)

        entry = entries[0]
        self.assertEqual(entry["event"], "agent_run")
        self.assertEqual(entry["agent_type"], "reviewer")
        self.assertEqual(entry["agent_id"], "sub-1")
        self.assertEqual(entry["stop_reason"], "end_turn")
        self.assertEqual(entry["session_id"], "test-session")

    def test_the_agents_output_is_not_recorded(self):
        # Counting runs, not transcribing work: a log that quietly accumulates model
        # output is a liability in a repo.
        self.subagent_stop()
        entry = self.trail_entries()[0]
        self.assertNotIn("last_assistant_message", entry)
        for value in entry.values():
            self.assertNotIn("auth.py", str(value))

    def test_runs_accumulate_in_order(self):
        for role in ("product-owner", "engineering-manager", "reviewer"):
            self.subagent_stop(agent_type=role)

        self.assertEqual(
            [e["agent_type"] for e in self.trail_entries()],
            ["product-owner", "engineering-manager", "reviewer"],
        )

    def test_a_payload_without_an_agent_type_records_nothing(self):
        self.subagent_stop(agent_type=None)
        self.assertEqual(self.trail_entries(), [])

    def test_the_trail_can_be_switched_off(self):
        self.write_config({"trail": False})
        self.subagent_stop()
        self.assertFalse(self.trail_file.exists())

    def test_no_spark_directory_means_no_trail(self):
        import shutil

        shutil.rmtree(self.root / ".spark")
        self.assertEqual(self.subagent_stop(), (0, ""))
        self.assertFalse(self.trail_file.exists())


class TestFeatureInference(TrailTestCase):
    def test_the_feature_comes_from_what_this_session_last_wrote(self):
        target = self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_approved.md")
        self.post_tool_use(target)

        self.subagent_stop()
        self.assertEqual(self.trail_entries()[0]["feature"], "weekly-stats")

    def test_it_is_null_before_the_session_has_written_anything(self):
        self.subagent_stop()
        self.assertIsNone(self.trail_entries()[0]["feature"])

    def test_another_sessions_writes_do_not_leak_in(self):
        target = self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_approved.md")
        self.post_tool_use(target, session_id="someone-else")

        self.subagent_stop()
        self.assertIsNone(self.trail_entries()[0]["feature"])


class TestCounting(TrailTestCase):
    def test_the_trail_reproduces_the_run_count_of_a_loop(self):
        # The point of the file: aSPARK's own metrics had to reach into Claude
        # Code's session logs for this number because the framework does not
        # record it. Six ceremonies, six lines, countable from the repo.
        roles = ["product-owner", "designer", "engineering-manager",
                 "reviewer", "qa-tester", "release-manager"]
        for role in roles:
            self.subagent_stop(agent_type=role)

        entries = self.trail_entries()
        self.assertEqual(len(entries), len(roles))
        self.assertEqual({e["agent_type"] for e in entries}, set(roles))


if __name__ == "__main__":
    unittest.main()
