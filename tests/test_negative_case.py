"""The negative case, first.

aSPARK Core's constitution requires it of any optional capability: "the negative
case runs first — in a repo where the capability is absent, nothing may change."
A project without `.spark/` must not be able to tell this plugin is installed.
"""

import unittest

from support import ACTIVITY_COMMANDS, GuardTestCase


class TestSilentWithoutSpark(GuardTestCase):
    def test_every_event_is_silent_and_writes_nothing(self):
        source = self.write_artifact("src/app.py", "print('hi')\n")
        before = self.tree()

        events = [
            ("pre-tool-use", {"cwd": str(self.root), "tool_name": "Write",
                              "tool_input": {"file_path": str(source)}}),
            ("post-tool-use", {"cwd": str(self.root), "tool_name": "Write",
                               "tool_input": {"file_path": str(source)}}),
            ("subagent-stop", {"cwd": str(self.root), "agent_type": "reviewer"}),
            ("session-start", {"cwd": str(self.root), "source": "startup"}),
        ]

        for command, payload in events:
            with self.subTest(event=command):
                code, out = self.run_hook(command, payload)
                self.assertEqual(code, 0)
                self.assertEqual(out, "")

        self.assertEqual(self.tree(), before, "the guard created or removed a file")

    def test_every_activity_event_is_silent_and_writes_nothing(self):
        before = self.tree()
        self.assertTrue(ACTIVITY_COMMANDS)

        for command in ACTIVITY_COMMANDS:
            with self.subTest(event=command):
                code, out = self.run_hook(command, {
                    "cwd": str(self.root), "session_id": "s1", "agent_id": "a1",
                    "agent_type": "reviewer", "reason": "clear",
                })
                self.assertEqual((code, out), (0, ""))

        self.assertEqual(self.tree(), before, "the guard created or removed a file")

    def test_write_inside_a_spark_lookalike_outside_the_root_is_ignored(self):
        # A directory literally named `.sparkle` must not be mistaken for `.spark`.
        target = self.write_artifact(".sparkle/spec.md", "# not ours\n")
        code, out = self.post_tool_use(target)
        self.assertEqual((code, out), (0, ""))
        self.assertFalse(self.ledger_file.exists())


class TestSilentWhenDisabled(GuardTestCase):
    def test_config_disables_everything(self):
        self.make_spark_project()
        self.write_config({"enabled": False})
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_approved.md")

        code, out = self.post_tool_use(target)
        self.assertEqual((code, out), (0, ""))
        self.assertFalse(self.ledger_file.exists())

    def test_config_disables_every_activity_event(self):
        self.make_spark_project()
        self.write_config({"enabled": False})
        for command in ACTIVITY_COMMANDS:
            with self.subTest(event=command):
                code, out = self.run_hook(command, {"cwd": str(self.root), "session_id": "s1"})
                self.assertEqual((code, out), (0, ""))
        self.assertFalse((self.root / ".spark" / ".guard").exists())

    def test_ledger_can_be_switched_off_alone(self):
        self.make_spark_project()
        self.write_config({"ledger": False})
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_approved.md")

        self.post_tool_use(target)
        self.assertFalse(self.ledger_file.exists())


if __name__ == "__main__":
    unittest.main()
