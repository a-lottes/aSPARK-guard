"""The live activity log at `.spark/.guard/activity.jsonl`.

What the team is doing right now: whether each session is busy, idle, waiting or
ended, and which subagents are running. It exists so a read-only cockpit can show
that from the project alone, without reaching into Claude Code's session logs.

Metadata only. Prompts, tool input, tool output, messages and thinking are in the
payloads and stay there — every value written here is either an id the harness
assigned, a timestamp, or drawn from a fixed list below. And facts only: nothing is
written on behalf of a session that went quiet, because a quiet session and a dead
one look the same from here.

Unlike the ledger and the trail, this file is local and never committed.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import ledger, trail

FORMAT_VERSION = 1

ACTIVITY_RELPATH = Path(".spark") / ".guard" / "activity.jsonl"

# One current file and one rotated generation: at most 2 x MAX_BYTES on disk.
MAX_BYTES = 2 * 1024 * 1024
LOCK_DEADLINE_S = 0.5

# Ignores itself too, so a repo adopting the guard sees no new untracked file. The
# ledger and the trail stay visible to git: they are the committed record.
GITIGNORE_TEXT = "/.gitignore\n/activity*\n"


# `SessionEnd.reason` values seen in the T1 spike. Anything else is `other`, so no
# harness-supplied string ever reaches the log unchecked.
END_REASONS = frozenset({"clear", "prompt_input_exit", "logout", "other"})


def activity_path(root: Path) -> Path:
    return Path(root) / ACTIVITY_RELPATH


def rotated_path(root: Path) -> Path:
    return activity_path(root).with_name("activity.jsonl.1")


def utc_now_ms() -> str:
    """UTC with milliseconds. The ledger's `utc_now` resolves to 1 s, too coarse to
    measure a run to ±50 ms — and it stays as it is, so the ledger format doesn't move."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _session_id(event: dict) -> str | None:
    value = event.get("session_id")
    return value if isinstance(value, str) and value else None


def record(root: Path, name: str, event: dict, **fields) -> dict | None:
    """Append one versioned line, or None if it could not be written."""
    entry = {
        "v": FORMAT_VERSION,
        "ts": utc_now_ms(),
        "event": name,
        "session_id": _session_id(event),
    }
    entry.update(fields)
    if not append_locked(activity_path(root), entry):
        return None
    return entry


def append_locked(path: Path, entry: dict) -> bool:
    """Append one line under the activity lock, rotating first if the file is full.

    Plain append mode keeps concurrent lines whole, but not a rotation: two writers
    that both see a full file would each rename it, and the second rename throws the
    first generation away. So every append and every rotation holds one lock. If the
    lock can't be had within the deadline the line is dropped — a hook never waits
    long on a log it doesn't need.
    """
    try:
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        guard_dir = Path(path).parent
        guard_dir.mkdir(parents=True, exist_ok=True)
        _ensure_gitignore(guard_dir)
        with open(guard_dir / "activity.lock", "a", encoding="utf-8") as lock:
            if not _acquire(lock):
                return False
            try:
                _repair_tail(path)
                if _size(path) >= MAX_BYTES:
                    os.replace(path, Path(path).with_name(Path(path).name + ".1"))
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _acquire(lock) -> bool:
    deadline = time.monotonic() + LOCK_DEADLINE_S
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)


def _size(path: Path) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _repair_tail(path: Path) -> None:
    """End a truncated last line, so the next one isn't glued onto it and lost too."""
    try:
        with open(path, "rb+") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                return
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                handle.write(b"\n")
    except FileNotFoundError:
        return


def _ensure_gitignore(guard_dir: Path) -> None:
    """Create `.spark/.guard/.gitignore` once. An existing file is never touched."""
    target = guard_dir / ".gitignore"
    if target.exists():
        return
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(GITIGNORE_TEXT)


def record_state(root: Path, event: dict, state: str, reason: str) -> dict | None:
    return record(root, "session_state", event, state=state, reason=reason)


def _agent_type(event: dict) -> str | None:
    value = event.get("agent_type")
    return value if isinstance(value, str) and value else None


def _agent_id(event: dict) -> str | None:
    value = event.get("agent_id")
    return value if isinstance(value, str) and value else None


def record_subagent_start(root: Path, event: dict) -> dict | None:
    """One line per subagent start. The harness's own helper agents carry an empty
    `agent_type` (seen in the T1 spike); like the trail, they are not recorded."""
    agent_type = _agent_type(event)
    if agent_type is None:
        return None
    return record(
        root,
        "subagent_start",
        event,
        agent_id=_agent_id(event),
        agent_type=agent_type,
        feature=trail.feature_for_session(root, _session_id(event)),
        task=None,
    )


def end_reason(event: dict) -> str:
    value = event.get("reason")
    return value if isinstance(value, str) and value in END_REASONS else "other"


def read_entries(root: Path):
    """Every line in write order: the rotated generation first, then the current file."""
    yield from ledger.read_jsonl(rotated_path(root))
    yield from ledger.read_jsonl(activity_path(root))
