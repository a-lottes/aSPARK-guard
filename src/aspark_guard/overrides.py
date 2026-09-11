"""Overrides: the documented way past a closed gate.

A gate can be overruled — but only through a line the human appends to
`.spark/<feature>/overrides.jsonl`, and only for the exact artifact state that
caused the block. The entry pins the SHA-256 of that artifact, so the moment the
artifact changes the override stops applying and has to be given again.

This is adSCAILE's `gate.override` → `override_decision_id` link rebuilt without a
server: there, an override is impossible without a decision-log entry carrying a
rationale. Here it is impossible without a committed line carrying one. Content
binding actually makes it stricter — adSCAILE ties the override to the gate, this
ties it to what the gate was looking at.

The honest limit is in the README: a hook cannot tell "the agent decided this" from
"the user dictated it". The goal is not *no override*, it is *no silent override*.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import artifacts, gitinfo

OVERRIDES_FILE = "overrides.jsonl"

# The placeholder the suggested line ships with. An entry still carrying it has not
# been filled in by anyone, so it grants nothing.
REASON_PLACEHOLDER = "<why>"


@dataclass(frozen=True)
class Override:
    rule: str
    artifact: str
    artifact_sha256: str
    reason: str

    def is_usable(self) -> bool:
        reason = (self.reason or "").strip()
        return bool(reason) and reason != REASON_PLACEHOLDER


def path_for(root: Path, feature: str) -> Path:
    return Path(root) / artifacts.SPARK_DIR / feature / OVERRIDES_FILE


def is_override_file(target: Path) -> bool:
    return Path(target).name == OVERRIDES_FILE


def read(root: Path, feature: str) -> list[Override]:
    """Parsed entries; malformed lines are skipped, never fatal."""
    entries = []
    try:
        raw = path_for(root, feature).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return entries

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        rule = data.get("rule")
        artifact = data.get("artifact")
        sha = data.get("artifact_sha256")
        if not all(isinstance(v, str) and v for v in (rule, artifact, sha)):
            continue
        entries.append(
            Override(
                rule=rule,
                artifact=artifact,
                artifact_sha256=sha,
                reason=data.get("reason") if isinstance(data.get("reason"), str) else "",
            )
        )
    return entries


def covers(root: Path, feature: str, rule_id: str, artifact_name: str,
           artifact_sha: str | None) -> bool:
    """True when a usable override exists for exactly this rule and artifact state.

    An override without a current hash to bind to never applies: if the artifact
    cannot be read, there is nothing to have been overruled.
    """
    if not artifact_sha:
        return False
    for entry in read(root, feature):
        if entry.rule != rule_id or entry.artifact != artifact_name:
            continue
        if entry.artifact_sha256 != artifact_sha:
            continue  # the artifact changed since — the override lapsed
        if entry.is_usable():
            return True
    return False


def suggest_line(root: Path, rule_id: str, artifact_name: str, artifact_sha: str,
                 timestamp: str) -> str:
    """The ready-to-paste entry, with the reason left for a human to write."""
    return json.dumps(
        {
            "ts": timestamp,
            "rule": rule_id,
            "artifact": artifact_name,
            "artifact_sha256": artifact_sha,
            "reason": REASON_PLACEHOLDER,
            "granted_by": gitinfo.user_name(root) or "<you>",
        },
        ensure_ascii=False,
    )
