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

Every violation names the artifacts whose state triggered it, each with the hash it
had at that moment — that pairing is what an override binds to (see overrides.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import artifacts, overrides

# Artifact file names as aSPARK Core instantiates them (constitution §5).
SPEC = "spec.md"
PLAN = "plan.md"
REVIEW = "review.md"
QA = "qa.md"
RELEASE = "release.md"

R_PLAN = "plan-requires-approved-spec"
R_QA = "qa-requires-passed-review"
R_RELEASE = "release-requires-green-gates"
R_OVERRIDE = "overrides-are-human-only"

ALL_RULES = (R_PLAN, R_QA, R_RELEASE, R_OVERRIDE)
GATED_ARTIFACTS = (PLAN, QA, RELEASE)

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
class Trigger:
    """One artifact whose state causes a block, and the hash it had when it did."""

    artifact: str
    detail: str
    sha256: str | None


@dataclass(frozen=True)
class Violation:
    rule_id: str
    headline: str
    triggers: tuple[Trigger, ...]
    remedy: str
    feature: str | None = None

    @property
    def state(self) -> str:
        return "; ".join(trigger.detail for trigger in self.triggers) + "."

    def message(self, override_lines: list[str] | None = None) -> str:
        lines = [
            f"aspark-guard: {self.headline}",
            f"  rule:  {self.rule_id}",
            f"  state: {self.state}",
            f"  {self.remedy}",
        ]
        if override_lines:
            where = f"{artifacts.SPARK_DIR}/{self.feature}/{overrides.OVERRIDES_FILE}"
            lines.append(
                f"  To overrule this, append this line to {where} YOURSELF — not via the "
                f"agent — and replace {overrides.REASON_PLACEHOLDER} with the reason:"
            )
            lines.extend(f"    {line}" for line in override_lines)
            lines.append(
                "  The override lapses as soon as the artifact it names changes."
            )
        lines.append(
            '  If this rule does not fit this project, set it to "warn" or "off" '
            'under "rules" in .spark/guard.json.'
        )
        return "\n".join(lines)


def _artifact_path(root: Path, feature: str, name: str) -> Path:
    return Path(root) / artifacts.SPARK_DIR / feature / name


def _status_of(root: Path, feature: str, name: str) -> str | None:
    return artifacts.read_status(_artifact_path(root, feature, name))


def _trigger_if_not(root: Path, feature: str, name: str, required: str) -> Trigger | None:
    """A trigger when the artifact is readable and not in the `required` status."""
    status = _status_of(root, feature, name)
    if status is None or status == required:
        return None
    return Trigger(
        artifact=name,
        detail=f"{artifacts.SPARK_DIR}/{feature}/{name} is `{status}`, not `{required}`",
        sha256=artifacts.sha256_file(_artifact_path(root, feature, name)),
    )


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


def _blocker_trigger(root: Path, feature: str) -> Trigger | None:
    path = _artifact_path(root, feature, QA)
    try:
        blockers = open_blockers(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if not blockers:
        return None
    return Trigger(
        artifact=QA,
        detail=(
            f"{artifacts.SPARK_DIR}/{feature}/{QA} still lists {len(blockers)} "
            f"open Blocker(s): {', '.join(blockers)}"
        ),
        sha256=artifacts.sha256_file(path),
    )


def _records_an_abort(root: Path, feature: str, incoming: str | None) -> bool:
    """True when this write is (or continues) an abort record."""
    if _status_of(root, feature, RELEASE) == ABORTED:
        return True
    if incoming and artifacts.parse_status(incoming) == ABORTED:
        return True
    return False


def _merge(triggers: list[Trigger]) -> tuple[Trigger, ...]:
    """Fold several findings about one artifact into a single trigger.

    A `qa.md` that is both `failed` and carries an open Blocker is still one
    artifact in one state, so one override settles it.
    """
    merged: dict[str, Trigger] = {}
    for trigger in triggers:
        existing = merged.get(trigger.artifact)
        if existing is None:
            merged[trigger.artifact] = trigger
        else:
            merged[trigger.artifact] = Trigger(
                artifact=trigger.artifact,
                detail=f"{existing.detail}; {trigger.detail}",
                sha256=existing.sha256,
            )
    return tuple(merged.values())


def _raw_evaluate(root: Path, target: Path, incoming: str | None) -> Violation | None:
    """The rule verdict before overrides are consulted."""
    feature = artifacts.feature_of(target, root)
    if feature is None:
        return None

    name = Path(target).name

    if overrides.is_override_file(target):
        return Violation(
            rule_id=R_OVERRIDE,
            headline="the override file is written by you, not by the agent.",
            triggers=(Trigger(artifact=overrides.OVERRIDES_FILE,
                              detail="an agent tried to write the override file",
                              sha256=None),),
            remedy="An override the agent can grant itself is not an override. Append "
                   "the line yourself, in an editor or from your own shell.",
            feature=feature,
        )

    if name == PLAN:
        trigger = _trigger_if_not(root, feature, SPEC, "approved")
        if trigger is None:
            return None
        return Violation(
            rule_id=R_PLAN,
            headline="a plan may not be written while the spec is not approved.",
            triggers=(trigger,),
            remedy=f"Close the gate first: take {SPEC} to `approved` (/story-time), then plan.",
            feature=feature,
        )

    if name == QA:
        trigger = _trigger_if_not(root, feature, REVIEW, "passed")
        if trigger is None:
            return None
        return Violation(
            rule_id=R_QA,
            headline="QA may not be recorded while the review has not passed.",
            triggers=(trigger,),
            remedy=f"Close the gate first: get {REVIEW} to `passed` (/peer-review), then test.",
            feature=feature,
        )

    if name == RELEASE:
        if _records_an_abort(root, feature, incoming):
            return None

        red = [
            _trigger_if_not(root, feature, REVIEW, "passed"),
            _trigger_if_not(root, feature, QA, "passed"),
            _blocker_trigger(root, feature),
        ]
        red = [trigger for trigger in red if trigger is not None]
        if not red:
            return None

        return Violation(
            rule_id=R_RELEASE,
            headline="a release may not be written over a red gate.",
            triggers=_merge(red),
            remedy="Close the gates first (/increment for the fixes, then /peer-review "
                   "and /demo-day), or record an abort by writing this release with "
                   "status `aborted`.",
            feature=feature,
        )

    return None


def uncovered(root: Path, violation: Violation) -> tuple[Trigger, ...]:
    """The triggers of a violation that no usable override accounts for."""
    if violation.feature is None or violation.rule_id == R_OVERRIDE:
        return violation.triggers
    return tuple(
        trigger
        for trigger in violation.triggers
        if not overrides.covers(
            root, violation.feature, violation.rule_id, trigger.artifact, trigger.sha256
        )
    )


def evaluate(root: Path, target: Path, incoming: str | None = None,
             apply_overrides: bool = True) -> Violation | None:
    """The violation this write would commit, or None if it may proceed.

    `incoming` is the content a Write carries, when the harness provides it. An Edit
    has no full content, which is why the abort check also looks at what is already
    on disk. With `apply_overrides=False` the raw verdict comes back even when an
    override settles it — that is how `check` can show what was overruled.
    """
    violation = _raw_evaluate(root, target, incoming)
    if violation is None or not apply_overrides:
        return violation

    remaining = uncovered(root, violation)
    if not remaining:
        return None
    if remaining == violation.triggers:
        return violation
    # Partly overridden: report only what is still open.
    return Violation(
        rule_id=violation.rule_id,
        headline=violation.headline,
        triggers=remaining,
        remedy=violation.remedy,
        feature=violation.feature,
    )


def pending(root: Path, feature: str) -> list[Violation]:
    """Every gate currently blocking in this feature, for the override suggestion."""
    found = []
    for name in GATED_ARTIFACTS:
        target = _artifact_path(root, feature, name)
        violation = evaluate(root, target)
        if violation is not None:
            found.append(violation)
    return found
