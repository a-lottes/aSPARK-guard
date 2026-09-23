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
import re
import time
import unicodedata
from contextlib import contextmanager
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


# The subagent tool's name (T1). Its PreToolUse carries the short description the
# main session gave the run; SubagentStart doesn't, so the label waits in a pending
# file for the start that follows.
SUBAGENT_TOOL = "Agent"
# What the harness reports on SubagentStart for a launch that named no type (QA B1).
DEFAULT_SUBAGENT_TYPE = "general-purpose"
TASK_MAX_CHARS = 80
PENDING_MAX_AGE_S = 60.0

# `SessionEnd.reason` values seen in the T1 spike. Anything else is `other`, so no
# harness-supplied string ever reaches the log unchecked.
END_REASONS = frozenset({"clear", "prompt_input_exit", "logout", "other"})


def activity_path(root: Path) -> Path:
    return Path(root) / ACTIVITY_RELPATH


def rotated_path(root: Path) -> Path:
    return activity_path(root).with_name("activity.jsonl.1")


def pending_path(root: Path) -> Path:
    return activity_path(root).with_name("activity.pending.jsonl")


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
        with _locked(Path(path).parent) as held:
            if not held:
                return False
            _repair_tail(path)
            if _size(path) >= MAX_BYTES:
                os.replace(path, Path(path).with_name(Path(path).name + ".1"))
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return True
    except (OSError, TypeError, ValueError):
        return False


@contextmanager
def _locked(guard_dir: Path):
    """Hold `.spark/.guard/activity.lock`; yields False if the deadline passed."""
    guard_dir.mkdir(parents=True, exist_ok=True)
    _ensure_gitignore(guard_dir)
    with open(guard_dir / "activity.lock", "a", encoding="utf-8") as lock:
        if not _acquire(lock):
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


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
    session_id = _session_id(event)
    agent_id = _agent_id(event)
    # A resume fires a new start with no launch before it (T1). It must not take a
    # label parked for someone else's launch, so only a first start claims one.
    seen, _ = _scan_agent(root, session_id, agent_id)
    return record(
        root,
        "subagent_start",
        event,
        agent_id=agent_id,
        agent_type=agent_type,
        feature=trail.feature_for_session(root, session_id),
        task=None if seen else _claim_task(root, session_id, agent_type),
    )


# An absolute path (two or more segments, so a slash command like "/peer-review"
# stays readable) or a home-relative one. The label is free text the model wrote,
# and a path in it would carry a user name into the log.
_PATH_TOKEN = re.compile(r"(?<![\w.:/])(?:~/\S*|/[^\s/]+/\S*)")
PATH_PLACEHOLDER = "<path>"


def sanitize_task(value) -> str | None:
    """The label as a single short line: no control characters, whitespace collapsed,
    paths replaced, at most TASK_MAX_CHARS. Anything that isn't a non-empty string is
    None."""
    if not isinstance(value, str):
        return None
    kept = "".join(" " if unicodedata.category(ch).startswith("C") else ch for ch in value)
    masked = _PATH_TOKEN.sub(PATH_PLACEHOLDER, kept)
    home = str(Path.home())
    if len(home) > 1:  # a home path glued to other text, which the token rule misses
        masked = masked.replace(home, PATH_PLACEHOLDER)
    collapsed = " ".join(masked.split())
    return collapsed[:TASK_MAX_CHARS].rstrip() or None


def record_pending_task(root: Path, event: dict) -> bool:
    """Park a subagent launch's short description until its SubagentStart arrives.

    Only `tool_input.description` and `subagent_type` are read — never the prompt.
    """
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return False
    agent_type = tool_input.get("subagent_type")
    entry = {
        "t": time.time(),
        "session_id": _session_id(event),
        "agent_type": agent_type if isinstance(agent_type, str) and agent_type
        else DEFAULT_SUBAGENT_TYPE,
        "task": sanitize_task(tool_input.get("description")),
    }
    return append_locked(pending_path(root), entry)


def _claim_task(root: Path, session_id: str | None, agent_type: str) -> str | None:
    """The label for this start, if exactly one fresh launch of this session and type
    is pending. Every matching entry is used up either way, so two same-type launches
    in parallel both get None rather than each other's label (AC-5.4)."""
    path = pending_path(root)
    if not path.exists():
        return None
    try:
        with _locked(path.parent) as held:
            if not held:
                return None
            now = time.time()
            keep, matched = [], []
            for entry in ledger.read_jsonl(path):
                t = entry.get("t")
                if not isinstance(t, (int, float)) or now - t > PENDING_MAX_AGE_S:
                    continue
                if entry.get("session_id") == session_id and entry.get("agent_type") == agent_type:
                    matched.append(entry)
                else:
                    keep.append(entry)
            tmp = path.with_name(path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as handle:
                for entry in keep:
                    handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            os.replace(tmp, path)
    except (OSError, TypeError, ValueError):
        return None
    if len(matched) != 1:
        return None
    task = matched[0].get("task")
    return task if isinstance(task, str) else None


def record_agent_run(root: Path, event: dict, stopped: datetime | None = None) -> dict | None:
    """One line per finish, with its duration when its start is in the log.

    The harness can report one run finished twice, with no new start in between
    (QA B4): the subagent answers, gets another message, and carries on. Last stop
    wins — every finish is measured from the agent's latest start, so the later line
    carries the real length and a reader takes the latest one (AC-2.2, AC-2.8).
    Lines already written stay as they are.

    No `stop_reason`: the harness doesn't send one (T1), and the guard never
    fills in a default. A stop without a recorded start gets `duration_ms: null`.
    """
    # When the stop fired, not when this line gets written: the caller takes it on
    # entry, before the trail and the scan below spend time of their own.
    stopped = stopped or datetime.now(timezone.utc)
    agent_type = _agent_type(event)
    if agent_type is None:
        return None
    session_id = _session_id(event)
    agent_id = _agent_id(event)
    _, start = _scan_agent(root, session_id, agent_id)
    duration_ms = None
    started = _parse_ts(start.get("ts")) if start else None
    if started is not None:
        elapsed = stopped - started
        duration_ms = max(0, int(elapsed.total_seconds() * 1000))
    # A run keeps the feature its start was given (AC-2.2): the subagent may well
    # have written the session's first artifact in between, which would change the
    # inference. Only a run without a recorded start is inferred here.
    feature = start.get("feature") if start else trail.feature_for_session(root, session_id)
    return record(
        root,
        "agent_run",
        event,
        agent_id=agent_id,
        agent_type=agent_type,
        feature=feature,
        duration_ms=duration_ms,
    )


def _scan_agent(root: Path, session_id: str | None, agent_id: str | None):
    """(seen, start): whether this agent has any line in this session, and its
    latest `subagent_start` line, or None.

    Paired from the log itself, so there is no second record to keep in step. A
    resumed agent reuses its `agent_id` but brings a start of its own (T1), so the
    latest start is the one a finish belongs to — also when an `agent_run` already
    follows it, because the last stop wins (C14). The substring check skips parsing
    every unrelated line.
    """
    if agent_id is None:
        return False, None
    seen = False
    opened = None
    for path in (rotated_path(root), activity_path(root)):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if agent_id not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("agent_id") != agent_id or entry.get("session_id") != session_id:
                        continue
                    seen = True
                    if entry.get("event") == "subagent_start":
                        opened = entry
        except OSError:
            continue
    return seen, opened


def _parse_ts(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def end_reason(event: dict) -> str:
    value = event.get("reason")
    return value if isinstance(value, str) and value in END_REASONS else "other"


def read_entries(root: Path):
    """Every line in write order: the rotated generation first, then the current file."""
    yield from ledger.read_jsonl(rotated_path(root))
    yield from ledger.read_jsonl(activity_path(root))
