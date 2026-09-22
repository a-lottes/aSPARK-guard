"""The activity log's write path: one lock, one rotated generation, kept out of git."""

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from support import REPO_ROOT, GuardTestCase

from aspark_guard import activity

WRITER = """
import sys
sys.path.insert(0, {src!r})
from pathlib import Path
from aspark_guard import activity
root = Path({root!r})
for i in range({count}):
    assert activity.record(root, "session_state", {{"session_id": {sid!r}}},
                           state="busy", reason="prompt", n=i) is not None
"""


class RotationTestCase(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.make_spark_project()
        self.current = activity.activity_path(self.root)
        self.rotated = activity.rotated_path(self.root)

    def prefill(self, size: int, path: Path | None = None) -> int:
        """Fill a log file with valid lines to at least `size` bytes; return the count."""
        path = path or self.current
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"v": 1, "event": "session_state", "pad": "x" * 200}) + "\n"
        count = -(-size // len(line))
        path.write_text(line * count, encoding="utf-8")
        return count

    def lines(self, path: Path) -> list[str]:
        if not path.exists():
            return []
        return [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def writer(self, sid: str, count: int) -> subprocess.Popen:
        code = WRITER.format(src=str(REPO_ROOT / "src"), root=str(self.root), count=count, sid=sid)
        return subprocess.Popen([sys.executable, "-c", code])


class TestConcurrentRotation(RotationTestCase):
    def test_two_writers_across_a_rotation_lose_and_break_nothing(self):
        prefilled = self.prefill(activity.MAX_BYTES - 50 * 1024)

        procs = [self.writer("s1", 500), self.writer("s2", 500)]
        for proc in procs:
            self.assertEqual(proc.wait(timeout=120), 0)

        self.assertTrue(self.rotated.exists(), "the 2 MB mark should have been crossed")
        every = self.lines(self.rotated) + self.lines(self.current)
        self.assertEqual(len(every), prefilled + 1000)

        parsed = [json.loads(line) for line in every]  # raises on a broken line
        for sid in ("s1", "s2"):
            numbers = [e["n"] for e in parsed if e.get("session_id") == sid]
            self.assertEqual(numbers, list(range(500)), f"{sid} lost or reordered lines")

    def test_a_second_rotation_keeps_exactly_one_generation(self):
        self.prefill(activity.MAX_BYTES, self.rotated)
        self.prefill(activity.MAX_BYTES + 10)

        activity.record(self.root, "session_state", {"session_id": "s1"}, state="idle", reason="stop")

        guard_dir = self.current.parent
        generations = sorted(p.name for p in guard_dir.glob("activity.jsonl*"))
        self.assertEqual(generations, ["activity.jsonl", "activity.jsonl.1"])
        self.assertEqual(len(self.lines(self.current)), 1)
        total = self.current.stat().st_size + self.rotated.stat().st_size
        self.assertLessEqual(total, 2 * activity.MAX_BYTES + 1024)

    def test_the_ledger_and_the_trail_are_never_rotated(self):
        ledger = self.root / ".spark" / ".guard" / "ledger.jsonl"
        self.prefill(activity.MAX_BYTES + 10, ledger)
        activity.record(self.root, "session_state", {"session_id": "s1"}, state="idle", reason="stop")
        self.assertFalse(ledger.with_name("ledger.jsonl.1").exists())
        self.assertGreater(ledger.stat().st_size, activity.MAX_BYTES)


class TestTruncatedTail(RotationTestCase):
    def test_an_append_after_a_truncated_line_still_parses(self):
        self.current.parent.mkdir(parents=True)
        self.current.write_text('{"v": 1, "event": "session_state"}\n{"v": 1, "ev', encoding="utf-8")

        activity.record(self.root, "session_state", {"session_id": "s1"}, state="idle", reason="stop")

        entries = list(activity.read_entries(self.root))
        self.assertEqual(len(entries), 2, "the truncated line is skipped, the new one kept")
        self.assertEqual(entries[-1]["state"], "idle")

    def test_reading_spans_the_rotated_generation_first(self):
        self.rotated.parent.mkdir(parents=True)
        self.rotated.write_text('{"n": 1}\n', encoding="utf-8")
        self.current.write_text('{"n": 2}\n', encoding="utf-8")
        self.assertEqual([e["n"] for e in activity.read_entries(self.root)], [1, 2])


class TestGitIgnore(RotationTestCase):
    def test_the_guard_dir_ignores_the_activity_files_and_itself(self):
        activity.record(self.root, "session_state", {"session_id": "s1"}, state="idle", reason="stop")
        gitignore = self.current.parent / ".gitignore"
        self.assertEqual(gitignore.read_text(encoding="utf-8"), activity.GITIGNORE_TEXT)

    def test_an_existing_gitignore_is_not_modified(self):
        gitignore = self.current.parent / ".gitignore"
        gitignore.parent.mkdir(parents=True)
        gitignore.write_text("# mine\n", encoding="utf-8")

        activity.record(self.root, "session_state", {"session_id": "s1"}, state="idle", reason="stop")
        self.assertEqual(gitignore.read_text(encoding="utf-8"), "# mine\n")

    @unittest.skipIf(shutil.which("git") is None, "git is not installed")
    def test_git_status_shows_ledger_and_trail_but_no_activity_file(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        spec = self.write_artifact(".spark/f/spec.md", "| **Status** | `draft` |\n")
        self.post_tool_use(spec)
        self.run_hook("subagent-stop", {"cwd": str(self.root), "session_id": "s1",
                                        "agent_id": "a1", "agent_type": "reviewer"})
        self.run_hook("stop", {"cwd": str(self.root), "session_id": "s1"})
        self.prefill(activity.MAX_BYTES + 10)
        self.run_hook("stop", {"cwd": str(self.root), "session_id": "s1"})
        self.assertTrue(self.rotated.exists())

        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=self.root, capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn(".spark/.guard/ledger.jsonl", status)
        self.assertIn(".spark/.guard/trail.jsonl", status)
        self.assertNotIn("activity", status)
        self.assertNotIn(".gitignore", status)


if __name__ == "__main__":
    unittest.main()
