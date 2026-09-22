"""Fail-open: nothing the guard meets may turn into a block or a crash.

A guard that raises when it is confused is worse than no guard — the user switches
it off, and then every gate is prompt-enforced again. So every hostile input below
must produce exit 0 and no output.
"""

import unittest

from support import ACTIVITY_COMMANDS, GuardTestCase


class TestHostileInput(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.make_spark_project()

    def test_malformed_or_empty_stdin(self):
        for raw in ("", "   ", "not json", "[]", "null", '{"tool_input": "a string"}', "{"):
            for command in ("pre-tool-use", "post-tool-use", "subagent-stop", "session-start"):
                with self.subTest(raw=raw, event=command):
                    code, out = self.run_hook(command, raw)
                    self.assertEqual(code, 0)
                    self.assertEqual(out, "")

    def test_activity_hooks_survive_malformed_or_empty_stdin(self):
        for raw in ("", "   ", "not json", "[]", "null", '{"session_id": 7}', "{"):
            for command in ACTIVITY_COMMANDS:
                with self.subTest(raw=raw, event=command):
                    self.assertEqual(self.run_hook(command, raw), (0, ""))

    def test_activity_hooks_survive_wrong_field_types(self):
        for event in ({"cwd": str(self.root), "session_id": ["x"]},
                      {"cwd": 42}, {"cwd": str(self.root), "agent_id": {}, "reason": 3}):
            for command in ACTIVITY_COMMANDS:
                with self.subTest(event=event, command=command):
                    self.assertEqual(self.run_hook(command, event), (0, ""))

    def test_an_unwritable_guard_directory_does_not_break_an_activity_hook(self):
        guard_dir = self.root / ".spark" / ".guard"
        guard_dir.mkdir(parents=True)
        guard_dir.chmod(0o500)
        self.addCleanup(guard_dir.chmod, 0o700)

        for command in ACTIVITY_COMMANDS:
            with self.subTest(event=command):
                self.assertEqual(
                    self.run_hook(command, {"cwd": str(self.root), "session_id": "s1"}), (0, "")
                )

    def test_every_event_has_a_handler(self):
        from aspark_guard import cli

        self.assertEqual(set(cli.EVENTS), set(cli.HANDLERS))

    def test_missing_fields(self):
        for event in ({}, {"cwd": str(self.root)}, {"tool_input": {}},
                      {"tool_input": {"file_path": ""}}, {"tool_input": {"file_path": None}}):
            with self.subTest(event=event):
                self.assertEqual(self.run_hook("post-tool-use", event), (0, ""))

    def test_paths_that_do_not_exist_or_are_not_files(self):
        self.assertEqual(self.post_tool_use(self.root / ".spark" / "ghost.md"), (0, ""))
        self.assertEqual(self.post_tool_use(self.root / ".spark"), (0, ""))

    def test_an_unknown_subcommand_does_nothing(self):
        self.assertEqual(self.run_hook("not-an-event", {}), (0, ""))

    def test_no_arguments_at_all(self):
        from aspark_guard import cli

        self.assertEqual(cli.main([]), 0)

    def test_a_corrupt_config_falls_back_to_defaults(self):
        self.write_artifact(".spark/guard.json", "{ this is not json")
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_approved.md")

        self.post_tool_use(target)
        self.assertEqual(len(self.ledger_entries()), 1, "defaults should still record")

    def test_a_config_with_wrong_types_is_survivable(self):
        self.write_artifact(".spark/guard.json", '{"enabled": "yes", "rules": "nope"}')
        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_approved.md")
        self.assertEqual(self.post_tool_use(target), (0, ""))

    def test_an_unwritable_guard_directory_does_not_break_the_write(self):
        # The ledger lives in the repo; if it cannot be written, the session must
        # carry on regardless — recording is a bonus, never a precondition.
        guard_dir = self.root / ".spark" / ".guard"
        guard_dir.mkdir(parents=True)
        guard_dir.chmod(0o500)
        self.addCleanup(guard_dir.chmod, 0o700)

        target = self.write_fixture_artifact(".spark/f/spec.md", "spec_approved.md")
        self.assertEqual(self.post_tool_use(target), (0, ""))

    def test_a_binary_artifact_is_handled(self):
        target = self.root / ".spark" / "f" / "diagram.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff\xfe")

        self.assertEqual(self.post_tool_use(target), (0, ""))
        self.assertEqual(len(self.ledger_entries()), 1)


if __name__ == "__main__":
    unittest.main()
