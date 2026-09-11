"""Reading `.spark/` artifacts: locating them, hashing them, parsing their status.

Every function here is total: on anything unexpected it returns None or an empty
result rather than raising. Callers rely on that — see the fail-open invariant in
README §Invariants.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

SPARK_DIR = ".spark"
GUARD_DIR = ".guard"

# How far up the tree we look for a `.spark/` directory before giving up. A repo
# nested deeper than this is not a repo we can reason about.
_MAX_WALK_UP = 20

# `| **Status** | `approved` |` in an artifact's header table.
_STATUS_ROW = re.compile(r"^\|\s*\*\*Status\*\*\s*\|(?P<value>.*)$", re.MULTILINE)
_BACKTICKED = re.compile(r"`([^`]+)`")

# An uninstantiated template lists every option on that row and nothing else:
# `draft` \| `design-checked` \| `approved` \| `rejected`. A real artifact that
# annotates its status — `handed-off` (`pr` mode — merge with the maintainer) —
# also holds several backticked values, so counting them is not enough to tell the
# two apart. Only the "choices and nothing but choices" shape means "no status yet".
_TEMPLATE_CHOICES = re.compile(r"^\s*`[^`]+`(?:\s*\\\|\s*`[^`]+`)+\s*$")


def find_spark_root(start: Path) -> Path | None:
    """Return the directory that contains a `.spark/` directory, at or above `start`.

    `start` may be a file or a directory, and need not exist — a Write to a
    not-yet-created file still has to resolve.
    """
    try:
        current = Path(start).expanduser().resolve()
    except (OSError, RuntimeError):
        return None

    if current.is_file():
        current = current.parent

    for _ in range(_MAX_WALK_UP):
        try:
            if (current / SPARK_DIR).is_dir():
                return current
        except OSError:
            return None
        if current.parent == current:
            break
        current = current.parent
    return None


def is_guard_own_file(path: Path, root: Path) -> bool:
    """True for the guard's own bookkeeping under `.spark/.guard/`.

    Recording our own writes would make the ledger describe itself.
    """
    rel = relative_to_root(path, root)
    if rel is None:
        return False
    return rel.startswith(f"{SPARK_DIR}/{GUARD_DIR}/")


def is_spark_artifact(path: Path, root: Path) -> bool:
    """True if `path` lives under `<root>/.spark/` and is not the guard's own file."""
    rel = relative_to_root(path, root)
    if rel is None:
        return False
    return rel.startswith(f"{SPARK_DIR}/") and not is_guard_own_file(path, root)


def relative_to_root(path: Path, root: Path) -> str | None:
    """POSIX-style path relative to the repo root, or None if it lies outside."""
    try:
        resolved = Path(path).expanduser().resolve()
        return resolved.relative_to(Path(root).resolve()).as_posix()
    except (ValueError, OSError, RuntimeError):
        return None


def feature_of(path: Path, root: Path) -> str | None:
    """The feature name from `.spark/<feature>/<artifact>`, or None.

    `.spark/constitution.md` is project-wide and has no feature.
    """
    rel = relative_to_root(path, root)
    if rel is None:
        return None
    parts = rel.split("/")
    if len(parts) < 3 or parts[0] != SPARK_DIR:
        return None
    if parts[1] == GUARD_DIR:
        return None
    return parts[1]


def sha256_file(path: Path) -> str | None:
    """Hex digest of the file's bytes, or None if it cannot be read."""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def parse_status(text: str) -> str | None:
    """The artifact's status from its header table, or None if not determinable.

    None covers three cases the caller must not distinguish: no status row, an
    unparseable row, and an uninstantiated template that still lists every option.
    """
    match = _STATUS_ROW.search(text or "")
    if match is None:
        return None

    # The row runs to the end of the line; drop the table's closing pipe so that a
    # template row keeps all of its escaped `\|` separators and stays detectable.
    cell = match.group("value").rstrip().removesuffix("|")
    if _TEMPLATE_CHOICES.match(cell):
        return None

    values = _BACKTICKED.findall(cell)
    if values:
        # The status is the first value; anything after it is annotation.
        return values[0].strip() or None

    plain = cell.strip()
    # A bare word is tolerated; anything with separators is not a single status.
    if plain and "|" not in plain and len(plain.split()) == 1:
        return plain
    return None


def read_status(path: Path) -> str | None:
    """`parse_status` over a file, for Markdown artifacts only."""
    if Path(path).suffix.lower() != ".md":
        return None
    try:
        return parse_status(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def iter_artifacts(root: Path):
    """Every tracked file under `<root>/.spark/`, excluding the guard's own dir.

    Yields absolute paths in sorted order so output is stable between runs.
    """
    spark = Path(root) / SPARK_DIR
    if not spark.is_dir():
        return
    try:
        candidates = sorted(spark.rglob("*"))
    except OSError:
        return
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
        except OSError:
            continue
        if is_guard_own_file(candidate, root):
            continue
        yield candidate
