"""Shared helpers: build a throwaway repo, run a hook the way Claude Code would."""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(REPO_ROOT / "src"))

from aspark_guard import cli  # noqa: E402


def fixture_text(name: str) -> str:
    return (FIXTURES / "artifacts" / name).read_text(encoding="utf-8")


class GuardTestCase(unittest.TestCase):
    """A temp directory per test, with helpers to shape it into a project."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="aspark-guard-test-")
        self.root = Path(self._tmp)
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)

    # --- building a project -------------------------------------------------

    def make_spark_project(self) -> Path:
        (self.root / ".spark").mkdir(parents=True, exist_ok=True)
        return self.root

    def write_artifact(self, relpath: str, content: str) -> Path:
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_fixture_artifact(self, relpath: str, fixture_name: str) -> Path:
        return self.write_artifact(relpath, fixture_text(fixture_name))

    def write_config(self, data: dict) -> Path:
        return self.write_artifact(".spark/guard.json", json.dumps(data))

    # --- running hooks ------------------------------------------------------

    def run_hook(self, command: str, payload: dict | str) -> tuple[int, str]:
        """Invoke a hook exactly as the harness does: JSON on stdin, capture stdout."""
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main([command], io.StringIO(raw))
        return code, buffer.getvalue()

    def post_tool_use(self, file_path: Path, **extra) -> tuple[int, str]:
        payload = {
            "session_id": "test-session",
            "cwd": str(self.root),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(file_path)},
            "tool_response": "ok",
        }
        payload.update(extra)
        return self.run_hook("post-tool-use", payload)

    def session_start(self, **extra) -> tuple[int, str]:
        payload = {
            "session_id": "test-session",
            "cwd": str(self.root),
            "hook_event_name": "SessionStart",
            "source": "startup",
        }
        payload.update(extra)
        return self.run_hook("session-start", payload)

    # --- reading results ----------------------------------------------------

    @property
    def ledger_file(self) -> Path:
        return self.root / ".spark" / ".guard" / "ledger.jsonl"

    def ledger_entries(self) -> list[dict]:
        if not self.ledger_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.ledger_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def tree(self) -> set[str]:
        """Every path in the temp repo, for asserting that nothing was created."""
        return {
            p.relative_to(self.root).as_posix()
            for p in self.root.rglob("*")
        }
