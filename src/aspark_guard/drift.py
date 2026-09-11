"""Detecting artifacts that changed outside the loop.

An artifact edited by hand in an editor never passes through a hook, so the ledger
has a gap. This finds the gap after the fact. It cannot prevent one — only a
substrate that refuses to treat the filesystem as authoritative could, and that is
the architecture aSPARK deliberately does not have.
"""

from __future__ import annotations

from pathlib import Path

from . import artifacts, ledger

# Beyond a handful, the list stops being a prompt and starts being a wall.
_MAX_LISTED = 10


def find_drifted(root: Path) -> list[str]:
    """Repo-relative paths whose current content differs from their last ledger entry.

    Files the ledger has never seen are not drift: they predate the guard's
    installation, which is the normal case on adoption and must stay quiet.
    """
    known = ledger.last_hash_by_path(root)
    if not known:
        return []

    drifted = []
    for path in artifacts.iter_artifacts(root):
        rel = artifacts.relative_to_root(path, root)
        if rel is None or rel not in known:
            continue
        current = artifacts.sha256_file(path)
        if current is not None and current != known[rel]:
            drifted.append(rel)
    return drifted


def format_notice(drifted: list[str]) -> str:
    """The context line for SessionStart, or an empty string when there is nothing to say."""
    if not drifted:
        return ""

    shown = drifted[:_MAX_LISTED]
    hidden = len(drifted) - len(shown)
    noun = "artifact" if len(drifted) == 1 else "artifacts"

    lines = [
        f"aspark-guard: {len(drifted)} .spark {noun} changed outside the loop "
        f"since the last recorded write:"
    ]
    lines.extend(f"  - {path}" for path in shown)
    if hidden > 0:
        lines.append(f"  - … and {hidden} more")
    lines.append(
        "Their current content is not what the ledger recorded, so any status they "
        "carry is unverified. Re-read them before relying on a gate."
    )
    return "\n".join(lines)
