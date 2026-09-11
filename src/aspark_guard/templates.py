"""The template contract: catching form drift where it is created.

aSPARK Core's constitution marks certain structures in `templates/` as protected,
because the sibling repo `aspark-graph` parses artifacts shaped by them and raises
`TemplateDriftError` on a mismatch — with **no version handshake** between the two
(Core's ROADMAP: *Blocked — template-version-marker*). So drift surfaces late, in
another repo, as a structural guess.

This checks the same structures on the producing side, the moment an artifact is
written. It never blocks: PostToolUse cannot deny, and a form question is not worth
a gate anyway. It reports, and the agent fixes it in the same turn.

Two rules keep it quiet enough to be worth having:

* **Drift, not completeness.** A structure is only checked once it has been started.
  A spec with no user stories yet is not a spec with malformed ones, and warning
  about it on every intermediate write would train everyone to ignore the warnings.
* **Extra columns are fine.** The constitution says so explicitly — the consumer
  matches headings by substring and tolerates additional ones. `plan.md` already
  ships two columns beyond the protected five.
"""

from __future__ import annotations

import re
from pathlib import Path

SPEC = "spec.md"
PLAN = "plan.md"
REVIEW = "review.md"
QA = "qa.md"
RELEASE = "release.md"

# Anything that opens like a story heading, so a malformed one is still caught.
_STORY_LINE = re.compile(r"^###\s+US-.*$", re.MULTILINE)
_STORY_OK = re.compile(r"^###\s+US-\d+\s+\([^)]+\):\s+\S")

# A checkbox line that names an acceptance criterion. Prose mentioning AC-1.1 is not
# one, which is why the trigger is the checkbox rather than the ID.
_AC_LINE = re.compile(r"^-\s+\[[ xX]\]\s+AC[^:]*:.*$", re.MULTILINE)
_AC_OK = re.compile(r"^-\s+\[[ xX]\]\s+AC-\d+\.\d+:\s+\S")

_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$", re.MULTILINE)
_TABLE_HEADER = re.compile(r"^\|(?P<cells>.+)\|\s*$", re.MULTILINE)
_ROW_ID = re.compile(r"^\|\s*(?P<id>[^|]+?)\s*\|")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _header_after(text: str, heading_substring: str) -> list[str] | None:
    """The first table header row following a heading that mentions `heading_substring`.

    Returns None when the heading is absent (nothing to check) or when it is present
    but carries no table yet (the section has been opened, not filled).
    """
    for heading in _HEADING.finditer(text):
        if heading_substring.lower() not in heading.group("title").lower():
            continue
        rest = text[heading.end():]
        # Stop at the next heading so a later table isn't mistaken for this one.
        next_heading = _HEADING.search(rest)
        section = rest[: next_heading.start()] if next_heading else rest
        row = _TABLE_HEADER.search(section)
        if row is None:
            return None
        return _cells(row.group(0))
    return None


def _missing_columns(header: list[str], required: tuple[str, ...]) -> list[str]:
    """Required column names absent from the header, matched by substring.

    Substring matching is the consumer's own rule, and it is why appending a column
    is safe.
    """
    joined = " | ".join(header).lower()
    return [name for name in required if name.lower() not in joined]


def _bad_row_ids(text: str, heading_substring: str, pattern: re.Pattern,
                 prefix: str) -> list[str]:
    """Row identifiers under a heading that don't match the expected ID form."""
    bad = []
    for heading in _HEADING.finditer(text):
        if heading_substring.lower() not in heading.group("title").lower():
            continue
        rest = text[heading.end():]
        next_heading = _HEADING.search(rest)
        section = rest[: next_heading.start()] if next_heading else rest
        for line in section.splitlines():
            match = _ROW_ID.match(line)
            if match is None:
                continue
            value = match.group("id").strip("* `")
            if not value or not value.upper().startswith(prefix):
                continue
            if not pattern.match(value):
                bad.append(value)
        break
    return bad


def _check_spec(text: str) -> list[str]:
    findings = []
    for line in _STORY_LINE.findall(text):
        if not _STORY_OK.match(line):
            findings.append(
                f"story heading is not `### US-<n> (<MoSCoW>): <title>`: {line.strip()!r}"
            )
    for line in _AC_LINE.findall(text):
        if not _AC_OK.match(line):
            findings.append(
                "acceptance criterion is not `- [ ] AC-<n>.<m>: <text>`, so aspark-graph "
                f"will not see it at all: {line.strip()[:70]!r}"
            )
    return findings


def _check_plan(text: str) -> list[str]:
    findings = []
    header = _header_after(text, "Task Breakdown")
    if header is not None:
        missing = _missing_columns(
            header, ("#", "Task", "Story", "Status", "Definition of Done")
        )
        if missing:
            findings.append(
                "Task Breakdown table is missing the protected column(s): "
                + ", ".join(missing)
            )
    for value in _bad_row_ids(text, "Task Breakdown", re.compile(r"^T\d+$"), "T"):
        findings.append(f"task id is not `T<n>`: {value!r}")
    return findings


def _check_review(text: str) -> list[str]:
    findings = []
    header = _header_after(text, "Findings")
    if header is not None:
        missing = _missing_columns(header, ("Severity", "Location", "Status"))
        if missing:
            findings.append(
                "Findings table is missing the protected column(s): " + ", ".join(missing)
            )
    for value in _bad_row_ids(text, "Findings", re.compile(r"^F\d+$"), "F"):
        findings.append(f"finding id is not `F<n>`: {value!r}")
    return findings


def _check_qa(text: str) -> list[str]:
    for row in _TABLE_HEADER.finditer(text):
        header = _cells(row.group(0))
        joined = " | ".join(header).lower()
        if "spec id" not in joined:
            continue
        if "result" not in joined:
            return [
                "the verification table carries `Spec ID` but not `Result` — "
                "aspark-graph matches both by name"
            ]
        return []
    return []


def _check_release(text: str) -> list[str]:
    # Only meaningful once a header table exists at all.
    if not re.search(r"^\|\s*\*\*[^*]+\*\*\s*\|", text, re.MULTILINE):
        return []
    missing = [
        name for name in ("Status", "Version")
        if not re.search(rf"^\|\s*\*\*{name}\*\*\s*\|", text, re.MULTILINE)
    ]
    if missing:
        return [
            "release header table is missing the protected row(s): " + ", ".join(missing)
        ]
    return []


_CHECKS = {
    SPEC: _check_spec,
    PLAN: _check_plan,
    REVIEW: _check_review,
    QA: _check_qa,
    RELEASE: _check_release,
}


def check_text(artifact_name: str, text: str) -> list[str]:
    """Contract findings for one artifact's content. Empty means no drift seen."""
    check = _CHECKS.get(artifact_name)
    if check is None:
        return []
    try:
        return check(text or "")
    except re.error:
        return []


def check_file(path: Path) -> list[str]:
    name = Path(path).name
    if name not in _CHECKS:
        return []
    try:
        return check_text(name, Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []


def format_findings(rel_path: str, findings: list[str]) -> str:
    if not findings:
        return ""
    lines = [
        f"aspark-guard: {rel_path} drifts from the aSPARK template contract "
        f"({len(findings)} finding(s)). aspark-graph parses these structures by name "
        f"and there is no version handshake, so drift here surfaces as a parse error "
        f"in another repo:"
    ]
    lines.extend(f"  - {finding}" for finding in findings)
    lines.append("  Nothing is blocked; fix it in the artifact you just wrote.")
    return "\n".join(lines)
