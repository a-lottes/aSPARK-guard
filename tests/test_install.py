"""Installation: the manifest's own command lines, executed the way the harness does.

Every other test calls `cli.main` or `bin/guard.py` directly. None of them proves the
string in `hooks/hooks.json` runs — and that string is the entire interface between
this plugin and Claude Code. A typo there is invisible to 129 passing tests and fatal
in a real session.

So these tests read the manifest, substitute `${CLAUDE_PLUGIN_ROOT}` the way the
harness does, and run the result through a shell — from a directory whose name
contains a space, because that is where naive quoting breaks.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from support import REPO_ROOT, GuardTestCase

MANIFEST = REPO_ROOT / "hooks" / "hooks.json"
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"

EXPECTED_EVENTS = {
    "PreToolUse", "PostToolUse", "SubagentStop", "SessionStart",
    "UserPromptSubmit", "Stop", "PermissionRequest", "SessionEnd",
    "SubagentStart",
}


def hook_commands() -> dict[str, str]:
    """Event name -> the command line the harness would run."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    commands = {}
    for event, matchers in manifest["hooks"].items():
        for matcher in matchers:
            for hook in matcher["hooks"]:
                commands[event] = hook["command"]
    return commands


class TestManifestShape(unittest.TestCase):
    def test_every_event_this_plugin_relies_on_is_wired(self):
        self.assertEqual(set(hook_commands()), EXPECTED_EVENTS)

    def test_every_hook_is_a_command_with_a_timeout(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for event, matchers in manifest["hooks"].items():
            for matcher in matchers:
                for hook in matcher["hooks"]:
                    with self.subTest(event=event):
                        self.assertEqual(hook["type"], "command")
                        # Invariant 3: the guard can never hang a session.
                        self.assertLessEqual(hook["timeout"], 10)

    def test_the_plugin_root_is_quoted_in_every_command(self):
        for event, command in hook_commands().items():
            with self.subTest(event=event):
                self.assertIn('"${CLAUDE_PLUGIN_ROOT}', command)

    def test_the_write_hooks_match_write_and_edit(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for event in ("PreToolUse", "PostToolUse"):
            self.assertEqual(manifest["hooks"][event][0]["matcher"], "Write|Edit")

    def test_tool_hooks_match_only_write_edit_and_the_subagent_tool(self):
        # AC-4.8: no hook on ordinary tool calls — every one would cost ~50 ms.
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        matchers = {
            event: [entry.get("matcher") for entry in manifest["hooks"][event]]
            for event in ("PreToolUse", "PostToolUse")
        }
        self.assertEqual(matchers, {"PreToolUse": ["Write|Edit", "Agent"],
                                    "PostToolUse": ["Write|Edit"]})

    def test_the_subagent_matcher_calls_the_gate_command_without_its_status_message(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        gate, label = manifest["hooks"]["PreToolUse"]
        self.assertEqual(label["hooks"][0]["command"], gate["hooks"][0]["command"])
        self.assertNotIn("statusMessage", label["hooks"][0])

    def test_notification_is_not_hooked_so_idle_reminders_never_start_the_guard(self):
        # D-T1-1: `waiting` comes from PermissionRequest; an `idle_prompt`
        # notification must not flip an idle session to waiting (AC-1.3).
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertNotIn("Notification", manifest["hooks"])

    def test_the_two_manifests_agree_on_the_plugin_name(self):
        plugin = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
        marketplace = json.loads(
            (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        names = {entry["name"] for entry in marketplace["plugins"]}
        self.assertIn(plugin["name"], names)


class TestInstalledCopyRuns(GuardTestCase):
    """A copy of the plugin under a path with a space, driven through a shell."""

    def setUp(self):
        super().setUp()
        self.plugin_root = self.root / "plugin cache" / "aspark guard"
        shutil.copytree(REPO_ROOT / "bin", self.plugin_root / "bin")
        shutil.copytree(REPO_ROOT / "src", self.plugin_root / "src")

        self.project = self.root / "someone elses project"
        (self.project / ".spark" / "weekly-stats").mkdir(parents=True)

    def run_hook_command(self, event: str, payload: dict) -> subprocess.CompletedProcess:
        command = hook_commands()[event].replace(
            "${CLAUDE_PLUGIN_ROOT}", str(self.plugin_root)
        )
        return subprocess.run(
            command,
            shell=True,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(self.project),
        )

    def artifact(self, name: str) -> Path:
        return self.project / ".spark" / "weekly-stats" / name

    def write(self, name: str, text: str) -> Path:
        path = self.artifact(name)
        path.write_text(text, encoding="utf-8")
        return path

    def test_all_four_commands_run_from_a_path_with_a_space(self):
        self.write("spec.md", "| **Status** | `approved` |\n")
        payloads = {
            "PreToolUse": {"cwd": str(self.project), "tool_name": "Write",
                           "tool_input": {"file_path": str(self.artifact("plan.md"))}},
            "PostToolUse": {"cwd": str(self.project), "tool_name": "Write",
                            "tool_input": {"file_path": str(self.artifact("spec.md"))},
                            "session_id": "s1"},
            "SubagentStop": {"cwd": str(self.project), "agent_type": "reviewer",
                             "session_id": "s1"},
            "SessionStart": {"cwd": str(self.project), "source": "startup"},
        }
        for event, payload in payloads.items():
            with self.subTest(event=event):
                result = self.run_hook_command(event, payload)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "", result.stderr)

    def test_the_activity_commands_run_from_a_path_with_a_space(self):
        for event in ("UserPromptSubmit", "Stop", "PermissionRequest", "SessionEnd",
                      "SubagentStart"):
            with self.subTest(event=event):
                result = self.run_hook_command(
                    event, {"cwd": str(self.project), "session_id": "s1",
                            "agent_id": "a1", "agent_type": "aspark:reviewer"}
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "", result.stderr)
                self.assertEqual(result.stdout, "")

        log = self.project / ".spark" / ".guard" / "activity.jsonl"
        events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e.get("state") for e in events[:4]], ["busy", "idle", "waiting", "ended"])
        self.assertEqual(events[4]["event"], "subagent_start")

    def test_a_fresh_install_needs_no_setup_at_all(self):
        # No config file, no directories created by hand, no build step: the first
        # write must simply be recorded.
        spec = self.write("spec.md", "| **Status** | `approved` |\n")
        result = self.run_hook_command(
            "PostToolUse",
            {"cwd": str(self.project), "tool_name": "Write",
             "tool_input": {"file_path": str(spec)}, "session_id": "s1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        ledger = self.project / ".spark" / ".guard" / "ledger.jsonl"
        self.assertTrue(ledger.exists(), "the ledger should be created on first write")
        entry = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(entry["path"], ".spark/weekly-stats/spec.md")
        self.assertEqual(entry["status"], "approved")

    def test_the_gate_denies_through_the_real_command_line(self):
        self.write("spec.md", "| **Status** | `draft` |\n")
        result = self.run_hook_command(
            "PreToolUse",
            {"cwd": str(self.project), "tool_name": "Write",
             "tool_input": {"file_path": str(self.artifact("plan.md"))}},
        )
        self.assertEqual(result.returncode, 0)
        decision = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_a_project_without_spark_stays_untouched(self):
        plain = self.root / "unrelated repo"
        (plain / "src").mkdir(parents=True)
        source = plain / "src" / "app.py"
        source.write_text("print('hi')\n", encoding="utf-8")
        before = {p.relative_to(plain).as_posix() for p in plain.rglob("*")}

        for event, payload in (
            ("PreToolUse", {"cwd": str(plain), "tool_name": "Write",
                            "tool_input": {"file_path": str(source)}}),
            ("PostToolUse", {"cwd": str(plain), "tool_name": "Write",
                             "tool_input": {"file_path": str(source)}}),
            ("SessionStart", {"cwd": str(plain), "source": "startup"}),
            ("SubagentStop", {"cwd": str(plain), "agent_type": "reviewer"}),
        ):
            result = self.run_hook_command(event, payload)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")

        after = {p.relative_to(plain).as_posix() for p in plain.rglob("*")}
        self.assertEqual(before, after)

    def test_only_bin_and_src_are_needed_at_runtime(self):
        # The copy above deliberately excludes tests/, docs and the manifests.
        # If anything at runtime reached for them, the tests above would fail.
        self.assertFalse((self.plugin_root / "tests").exists())
        self.assertFalse((self.plugin_root / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
