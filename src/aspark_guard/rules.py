"""The gate rules: phase preconditions, checked on the tool call itself.

Each rule answers one question — may this artifact be written, given the state of
the artifact before it? The rules deliberately know nothing about which ceremony is
running; everything is derived from the path and from files already on disk, which
is what lets a hook enforce them at all.

Two conservative choices run through all of them, both load-bearing:

* **A missing prerequisite never blocks.** "There is no spec" is indistinguishable
  from "this project doesn't keep one", and aSPARK's own skills already refuse to
  start without their input. The guard enforces the *ordering* of a loop that is
  being run; it does not mandate that the loop be run. Verified against a real
  feature (`lean-rounds`) that has a released `release.md` and no `qa.md` at all.
* **An unreadable status never blocks.** If the header table cannot be parsed, the
  guard has no fact to act on. See the fail-open invariant in README §Invariants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import artifacts

# Artifact file names as aSPARK Core instantiates them (constitution §5).
SPEC = "spec.md"
PLAN = "plan.md"
REVIEW = "review.md"
QA = "qa.md"
RELEASE = "release.md"

R_PLAN = "plan-requires-approved-spec"
R_QA = "qa-requires-passed-review"
R_RELEASE = "release-requires-green-gates"

# A release that records an abort is a legitimate write over red gates — refusing it
# would block the very artifact that documents why nothing shipped.
ABORTED = "aborted"

# `/demo-day`'s findings table: | # | Severity | Steps | Expected vs. observed | Status |
_FINDING_ROW = re.compile(r"^\|\s*B\d+\s*\|(?P<rest>.*)$", re.MULTILINE)

# The QA template is explicit that `open` is matched by exact equality — "a suffixed
# or renamed value silently drops the finding from every open-findings view". Real
# artifacts carry severities like `Blocker → superseded` and statuses like
# `fixed r6, reconfirmed r8`, so severity is matched loosely and status strictly.
_OPEN = "open"


@dataclass(frozen=True)
class Violation:
    rule_id: str
    headline: str
    state: str
    remedy: str

    def message(self) -> str:
        return (
            f"aspark-guard: {self.headline}\n"
            f"  rule:  {self.rule_id}\n"
            f"  state: {self.state}\n"
            f"  {self.remedy}\n"
            f"  If this rule does not fit this project, set it to \"warn\" or \"off\" "
            f'under "rules" in .spark/guard.json.'
        )


def _status_of(root: Path, feature: str, name: str) -> str | None:
    return artifacts.read_status(Path(root) / artifacts.SPARK_DIR / feature / name)


def _blocks(root: Path, feature: str, name: str, required: str) -> str | None:
    """The artifact's status when it is readable and not `required`, else None."""
    status = _status_of(root, feature, name)
    if status is None or status == required:
        return None
    return status


def open_blockers(text: str) -> list[str]:
    """IDs of findings whose severity mentions Blocker and whose status is `open`."""
    found = []
    for match in _FINDING_ROW.finditer(text or ""):
        cells = [cell.strip() for cell in match.group(0).strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        finding_id, severity, status = cells[0], cells[1], cells[-1]
        if "blocker" not in severity.lower():
            continue
        if status.strip("` ").lower() == _OPEN:
            found.append(finding_id)
    return found


def _qa_open_blockers(root: Path, feature: str) -> list[str]:
    path = Path(root) / artifacts.SPARK_DIR / feature / QA
    try:
        return open_blockers(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []


def _records_an_abort(root: Path, feature: str, incoming: str | None) -> bool:
    """True when this write is (or continues) an abort record."""
    if _status_of(root, feature, RELEASE) == ABORTED:
        return True
    if incoming and artifacts.parse_status(incoming) == ABORTED:
        return True
    return False


def evaluate(root: Path, target: Path, incoming: str | None = None) -> Violation | None:
    """The violation this write would commit, or None if it may proceed.

    `incoming` is the content a Write carries, when the harness provides it. An Edit
    has no full content, which is why the abort check also looks at what is already
    on disk.
    """
    feature = artifacts.feature_of(target, root)
    if feature is None:
        return None

    name = Path(target).name
    rel = f"{artifacts.SPARK_DIR}/{feature}"

    if name == PLAN:
        status = _blocks(root, feature, SPEC, "approved")
        if status is not None:
            return Violation(
                rule_id=R_PLAN,
                headline="a plan may not be written while the spec is not approved.",
                state=f"{rel}/{SPEC} is `{status}`, not `approved`.",
                remedy=f"Close the gate first: take {SPEC} to `approved` (/story-time), then plan.",
            )
        return None

    if name == QA:
        status = _blocks(root, feature, REVIEW, "passed")
        if status is not None:
            return Violation(
                rule_id=R_QA,
                headline="QA may not be recorded while the review has not passed.",
                state=f"{rel}/{REVIEW} is `{status}`, not `passed`.",
                remedy=f"Close the gate first: get {REVIEW} to `passed` (/peer-review), then test.",
            )
        return None

    if name == RELEASE:
        if _records_an_abort(root, feature, incoming):
            return None

        red = []
        review_status = _blocks(root, feature, REVIEW, "passed")
        if review_status is not None:
            red.append(f"{rel}/{REVIEW} is `{review_status}`, not `passed`")
        qa_status = _blocks(root, feature, QA, "passed")
        if qa_status is not None:
            red.append(f"{rel}/{QA} is `{qa_status}`, not `passed`")
        blockers = _qa_open_blockers(root, feature)
        if blockers:
            listed = ", ".join(blockers)
            red.append(f"{rel}/{QA} still lists {len(blockers)} open Blocker(s): {listed}")

        if red:
            return Violation(
                rule_id=R_RELEASE,
                headline="a release may not be written over a red gate.",
                state="; ".join(red) + ".",
                remedy="Close the gates first (/increment for the fixes, then /peer-review "
                       "and /demo-day), or record an abort by writing this release with "
                       "status `aborted`.",
            )
        return None

    return None
