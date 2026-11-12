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

from fnmatch import fnmatch

from . import artifacts, ledger, overrides

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
R_CODE = "code-requires-approved-plan"

ALL_RULES = (R_PLAN, R_QA, R_RELEASE, R_OVERRIDE, R_CODE)

# R5 scopes. "session": only a session that itself started a loop is held to it.
# "always": the project decided that code changes only under an approved plan.
SCOPE_SESSION = "session"
SCOPE_ALWAYS = "always"
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


# --- R5: code waits for an approved plan --------------------------------------
#
# Unlike R1-R3 the target here is not a `.spark/` artifact, so there is no path to
# read the feature from. The rule takes it from the ledger instead: which features
# did *this session* write a spec or plan for? That is a fact on disk, not a guess
# about which ceremony is running.


def _later_artifact_exists(root: Path, feature: str) -> bool:
    return any(_artifact_path(root, feature, name).is_file() for name in (REVIEW, QA, RELEASE))


def _plan_trigger(root: Path, feature: str) -> Trigger | None:
    """Why this feature's plan does not yet allow code, or None if it does (or is unreadable)."""
    plan = _artifact_path(root, feature, PLAN)
    if plan.is_file():
        return _trigger_if_not(root, feature, PLAN, "approved")
    spec = _artifact_path(root, feature, SPEC)
    if not spec.is_file():
        return None
    return Trigger(
        artifact=SPEC,
        detail=f"{artifacts.SPARK_DIR}/{feature}/{SPEC} has no {PLAN} beside it yet",
        sha256=artifacts.sha256_file(spec),
    )


def session_features(root: Path, session_id: str | None) -> list[str]:
    """Features whose spec or plan this session wrote, in first-write order."""
    if not isinstance(session_id, str) or not session_id:
        return []
    found: list[str] = []
    for entry in ledger.read_entries(root):
        if entry.get("session_id") != session_id:
            continue
        feature = entry.get("feature")
        path = entry.get("path")
        if not isinstance(feature, str) or not isinstance(path, str):
            continue
        if path.rsplit("/", 1)[-1] not in (SPEC, PLAN):
            continue
        if feature not in found:
            found.append(feature)
    return found


def _all_features(root: Path) -> list[str]:
    spark = Path(root) / artifacts.SPARK_DIR
    try:
        return sorted(
            child.name for child in spark.iterdir()
            if child.is_dir() and child.name != artifacts.GUARD_DIR
        )
    except OSError:
        return []


def _is_exempt(rel: str, exempt) -> bool:
    return any(isinstance(pattern, str) and fnmatch(rel, pattern) for pattern in exempt or ())


def evaluate_code_write(root: Path, target: Path, session_id: str | None,
                        scope: str = SCOPE_SESSION, exempt=()) -> Violation | None:
    """The violation a write to a file *outside* `.spark/` would commit, or None.

    "session" scope: this session wrote a spec or plan, and none of the features it
    wrote for has an approved plan yet. A session that never touched a trail is never
    held, and neither is one that is building a feature whose plan is approved while
    it drafts the next one.

    "always" scope: no feature in the project has an approved plan that is still
    unreleased. This is the only form that also catches code written before any
    spec exists, and it is opt-in because it holds every session in the project.
    """
    rel = artifacts.relative_to_root(target, root)
    if rel is None or rel.startswith(f"{artifacts.SPARK_DIR}/") or _is_exempt(rel, exempt):
        return None

    if scope == SCOPE_ALWAYS:
        features = _all_features(root)
        for feature in features:
            if (_status_of(root, feature, PLAN) == "approved"
                    and not _artifact_path(root, feature, RELEASE).is_file()):
                return None
        # Unreadable plans are facts the guard does not have: stay out of the way.
        for feature in features:
            plan = _artifact_path(root, feature, PLAN)
            if plan.is_file() and _status_of(root, feature, PLAN) is None:
                return None
        return Violation(
            rule_id=R_CODE,
            headline="this project allows code changes only under an approved plan.",
            triggers=(Trigger(
                artifact=PLAN,
                detail=f"no feature under {artifacts.SPARK_DIR}/ has an approved, unreleased {PLAN}",
                sha256=None,
            ),),
            remedy=f"Take a feature to an approved {PLAN} first (/story-time, then "
                   f"/sprint-plan), then write code.",
            feature=None,
        )

    features = session_features(root, session_id)
    if not features:
        return None

    blocking: list[tuple[str, Trigger]] = []
    for feature in features:
        if _later_artifact_exists(root, feature):
            return None  # past planning: review, QA or release already exist
        trigger = _plan_trigger(root, feature)
        if trigger is None:
            return None  # an approved (or unreadable) plan this session works under
        blocking.append((feature, trigger))

    feature, trigger = blocking[0]
    return Violation(
        rule_id=R_CODE,
        headline="code may not be written while the plan of the feature this session "
                 "started is not approved.",
        triggers=(trigger,),
        remedy=f"Close the gate first: get {PLAN} to `approved` (/sprint-plan), then build.",
        feature=feature,
    )
