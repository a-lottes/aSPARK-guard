"""The append-only hash ledger at `.spark/.guard/ledger.jsonl`.

One line per artifact write: what was written, what it hashed to, what status it
carried at that moment. The previous hash of a file is the previous line for that
file — the chain is the record, so no entry stores a "before" value.

Why this is not redundant with git: git only sees what gets committed, and
collapses every intermediate state of a commit into one diff. The ledger dates
each status change on its own, which is what turns "spec.md was approved when
plan.md was written" from plausible into checkable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import artifacts, gitinfo

LEDGER_RELPATH = Path(".spark") / ".guard" / "ledger.jsonl"


def ledger_path(root: Path) -> Path:
    return Path(root) / LEDGER_RELPATH


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_to(path: Path, entry: dict) -> bool:
    """Append one JSON line to an append-only log. False if it could not be written.

    Shared with the agent-run trail, which has the same shape and the same rules.
    """
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        # Append mode on a POSIX filesystem keeps concurrent writers from
        # interleaving whole lines; the guard never rewrites existing ones.
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return True
    except (OSError, TypeError, ValueError):
        return False


def read_jsonl(path: Path):
    """Yield parsed entries in file order, skipping any line that does not parse."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    yield parsed
    except OSError:
        return


def append(root: Path, entry: dict) -> bool:
    return append_to(ledger_path(root), entry)


def read_entries(root: Path):
    yield from read_jsonl(ledger_path(root))


def last_hash_by_path(root: Path) -> dict:
    """Map of repo-relative path -> sha256 of its most recent ledger entry."""
    latest = {}
    for entry in read_entries(root):
        path = entry.get("path")
        sha = entry.get("sha256")
        if isinstance(path, str) and isinstance(sha, str):
            latest[path] = sha
    return latest


def record_write(root: Path, file_path: Path, event_meta: dict) -> dict | None:
    """Build and append the entry for a write to `file_path`.

    Returns the entry, or None when nothing was recorded: the file is not a
    `.spark/` artifact, it is unreadable, or its content is byte-identical to the
    last entry for it (a no-op Edit, or a write the tool ultimately failed to make).
    """
    if not artifacts.is_spark_artifact(file_path, root):
        return None

    rel = artifacts.relative_to_root(file_path, root)
    if rel is None:
        return None

    sha = artifacts.sha256_file(file_path)
    if sha is None:
        return None

    if last_hash_by_path(root).get(rel) == sha:
        return None

    entry = {
        "ts": utc_now(),
        "event": "artifact_write",
        "feature": artifacts.feature_of(file_path, root),
        "path": rel,
        "sha256": sha,
        "status": artifacts.read_status(file_path),
        "git_head": gitinfo.head(root),
        "session_id": event_meta.get("session_id"),
        "agent_type": event_meta.get("agent_type"),
    }
    if not append(root, entry):
        return None
    return entry
