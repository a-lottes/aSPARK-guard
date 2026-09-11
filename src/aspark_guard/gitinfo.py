"""The one place the guard shells out.

`git rev-parse` is read-only, takes milliseconds and is the only way to anchor a
ledger entry to a commit. If git is missing, the repo has no commits, or the call
is slow, the entry simply carries `null` — the ledger stays useful without it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_TIMEOUT_SECONDS = 2


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def head(root: Path) -> str | None:
    """Short SHA of HEAD, or None if it cannot be determined."""
    return _git(root, "rev-parse", "--short", "HEAD")


def user_name(root: Path) -> str | None:
    """The configured git user, used to pre-fill who granted an override."""
    return _git(root, "config", "user.name")
