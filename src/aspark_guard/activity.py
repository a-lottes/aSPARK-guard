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

from datetime import datetime, timezone
from pathlib import Path

from . import ledger

FORMAT_VERSION = 1

ACTIVITY_RELPATH = Path(".spark") / ".guard" / "activity.jsonl"


def activity_path(root: Path) -> Path:
    return Path(root) / ACTIVITY_RELPATH


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
    if not ledger.append_to(activity_path(root), entry):
        return None
    return entry


def record_state(root: Path, event: dict, state: str, reason: str) -> dict | None:
    return record(root, "session_state", event, state=state, reason=reason)


def read_entries(root: Path):
    yield from ledger.read_jsonl(activity_path(root))
