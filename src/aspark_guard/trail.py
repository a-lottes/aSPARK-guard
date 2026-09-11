"""The agent-run trail at `.spark/.guard/trail.jsonl`.

One line per subagent that finishes. It exists because aSPARK's own metrics had to
reach into Claude Code's session logs to count role-agent runs — the framework does
not record them itself. A line per run makes that number come from the project.

What is deliberately not recorded: the agent's output. `last_assistant_message` is
in the payload and stays there. The purpose is counting runs, not transcribing work,
and a log that quietly accumulates model output is a liability in a repo.
"""

from __future__ import annotations

from pathlib import Path

from . import ledger

TRAIL_RELPATH = Path(".spark") / ".guard" / "trail.jsonl"


def trail_path(root: Path) -> Path:
    return Path(root) / TRAIL_RELPATH


def _feature_for_session(root: Path, session_id: str | None) -> str | None:
    """Best guess at which feature this run belongs to.

    A SubagentStop payload carries no file path, so the feature is inferred from the
    last artifact this session wrote. That is a heuristic, not an observation: an
    agent that wrote nothing inherits whatever the session touched last. It is right
    in the ordinary case — one session works one feature — and null before the
    session has written anything at all.
    """
    if not session_id:
        return None
    feature = None
    for entry in ledger.read_entries(root):
        if entry.get("session_id") == session_id and entry.get("feature"):
            feature = entry["feature"]
    return feature


def record_run(root: Path, event: dict) -> dict | None:
    """Append the entry for one finished subagent, or None if there is nothing to say."""
    agent_type = event.get("agent_type")
    if not isinstance(agent_type, str) or not agent_type:
        return None

    session_id = event.get("session_id")
    entry = {
        "ts": ledger.utc_now(),
        "event": "agent_run",
        "agent_type": agent_type,
        "agent_id": event.get("agent_id"),
        "feature": _feature_for_session(root, session_id if isinstance(session_id, str) else None),
        "stop_reason": event.get("stop_reason"),
        "session_id": session_id,
    }
    if not ledger.append_to(trail_path(root), entry):
        return None
    return entry


def read_entries(root: Path):
    yield from ledger.read_jsonl(trail_path(root))
