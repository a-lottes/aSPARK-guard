"""NFR-2: no content ever reaches the activity files.

Every content-carrying field of every hooked payload gets a unique marker. After a
full sequence of events — forced across a rotation — none of the markers, no home
directory and no absolute path may appear in the current, rotated or pending file.
"""

import unittest
from pathlib import Path
from unittest import mock

from support import GuardTestCase

from aspark_guard import activity

MARKERS = {
    "prompt": "MARKER_PROMPT_1f3a",
    "tool_content": "MARKER_TOOL_CONTENT_9c2e",
    "subagent_prompt": "MARKER_SUBAGENT_PROMPT_77ab",
    "tool_output": "MARKER_TOOL_OUTPUT_5d10",
    "last_message": "MARKER_LAST_MESSAGE_c0de",
    "thinking": "MARKER_THINKING_4e4e",
    "notification": "MARKER_NOTIFICATION_8a8a",
    "command": "MARKER_COMMAND_2b2b",
    "transcript": "MARKER_TRANSCRIPT_6f6f",
}


class TestNoContentReachesTheLog(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.make_spark_project()

    def base(self, event: str) -> dict:
        return {
            "session_id": "s1",
            "cwd": str(self.root),
            "hook_event_name": event,
            "transcript_path": f"{self.root}/{MARKERS['transcript']}.jsonl",
            "thinking": MARKERS["thinking"],
            "last_assistant_message": MARKERS["last_message"],
            "message": MARKERS["notification"],
        }

    def sequence(self):
        spec = self.write_artifact(".spark/f/spec.md", "| **Status** | `draft` |\n")
        return [
            ("user-prompt-submit", {**self.base("UserPromptSubmit"), "prompt": MARKERS["prompt"]}),
            ("pre-tool-use", {**self.base("PreToolUse"), "tool_name": "Agent",
                              "tool_input": {"description": "Write the spec",
                                             "prompt": MARKERS["subagent_prompt"],
                                             "subagent_type": "aspark:product-owner"}}),
            ("subagent-start", {**self.base("SubagentStart"), "agent_id": "a1",
                                "agent_type": "aspark:product-owner"}),
            ("post-tool-use", {**self.base("PostToolUse"), "tool_name": "Write",
                               "tool_input": {"file_path": str(spec),
                                              "content": MARKERS["tool_content"]},
                               "tool_response": MARKERS["tool_output"]}),
            ("permission-request", {**self.base("PermissionRequest"), "tool_name": "Bash",
                                    "tool_input": {"command": MARKERS["command"],
                                                   "description": MARKERS["command"]},
                                    "permission_suggestions": [{"rule": MARKERS["command"]}]}),
            ("subagent-stop", {**self.base("SubagentStop"), "agent_id": "a1",
                               "agent_type": "aspark:product-owner",
                               "agent_transcript_path": MARKERS["transcript"]}),
            ("stop", self.base("Stop")),
            ("session-end", {**self.base("SessionEnd"), "reason": MARKERS["notification"]}),
        ]

    def activity_files(self) -> dict[str, str]:
        guard = self.root / ".spark" / ".guard"
        return {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(guard.glob("activity*"))
            if path.is_file()
        }

    def test_no_marker_home_or_absolute_path_in_any_activity_file(self):
        # A tiny cap forces the rotation mid-sequence, so the rotated file is checked too.
        with mock.patch.object(activity, "MAX_BYTES", 300):
            for _ in range(3):
                for command, payload in self.sequence():
                    with self.subTest(command=command):
                        self.assertEqual(self.run_hook(command, payload), (0, ""))
            # A launch nobody claimed stays in the pending file; check that one too.
            command, payload = self.sequence()[1]
            self.run_hook(command, payload)

        files = self.activity_files()
        self.assertIn("activity.jsonl", files)
        self.assertIn("activity.jsonl.1", files, "the rotation should have happened")
        self.assertIn("activity.pending.jsonl", files)

        for name, text in files.items():
            for field, marker in MARKERS.items():
                with self.subTest(file=name, field=field):
                    self.assertNotIn(marker, text)
            with self.subTest(file=name, check="paths"):
                self.assertNotIn(str(Path.home()), text)
                self.assertNotIn(str(self.root), text)
                self.assertNotIn('"/', text, "no value may start like an absolute path")

    def test_the_only_free_text_is_the_short_label(self):
        # The label is the one field taken from a payload's text (US-5), and it is the
        # description the main session wrote for the run — never its prompt.
        for command, payload in self.sequence():
            self.run_hook(command, payload)
        [start] = [e for e in activity.read_entries(self.root) if e["event"] == "subagent_start"]
        self.assertEqual(start["task"], "Write the spec")


if __name__ == "__main__":
    unittest.main()
