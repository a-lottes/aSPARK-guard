"""Hook dispatch.

One entry point, one subcommand per hook event. Two rules govern everything below:

1. Degrade to silence — no `.spark/` directory means no output, no files, nothing.
   A repo that does not use aSPARK must not notice this plugin is installed.
2. Fail open — any unexpected input, missing file or exception lets the action
   proceed. A guard that blocks when it is unsure trains people to switch it off,
   and then it guards nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import artifacts, config, drift, ledger, rules

EVENTS = ("pre-tool-use", "post-tool-use", "subagent-stop", "session-start")


def _read_event(stream) -> dict:
    """Parse the hook payload from stdin; an unreadable payload is an empty one."""
    try:
        raw = stream.read()
    except (OSError, ValueError):
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _written_path(event: dict) -> Path | None:
    """The file a Write/Edit targets, from `tool_input.file_path`."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    value = tool_input.get("file_path")
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


def _incoming_content(event: dict) -> str | None:
    """The full content a Write carries. An Edit has none — only a replacement."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    content = tool_input.get("content")
    return content if isinstance(content, str) else None


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")


def _deny(reason: str) -> None:
    _emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })


def _note(context: str) -> None:
    """Allow, but put the finding in front of the model."""
    _emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": context,
        }
    })


def _root_for(event: dict, hint: Path | None = None) -> Path | None:
    """Locate the repo root, preferring the file being written over the cwd.

    A Write can target a repo other than the one the session started in; the file's
    own location is the more reliable signal.
    """
    if hint is not None:
        root = artifacts.find_spark_root(hint)
        if root is not None:
            return root
    cwd = event.get("cwd")
    if isinstance(cwd, str) and cwd:
        return artifacts.find_spark_root(Path(cwd))
    return None


# --- handlers ---------------------------------------------------------------


def handle_pre_tool_use(event: dict) -> int:
    """Deny a write that would violate a phase precondition.

    Exit stays 0 in every branch: the decision travels in the JSON, which is the
    only way to give the user a reason they can read.
    """
    target = _written_path(event)
    if target is None:
        return 0

    root = _root_for(event, hint=target)
    if root is None:
        return 0

    settings = config.load(root)
    violation = rules.evaluate(root, target, _incoming_content(event))
    if violation is None:
        return 0

    mode = settings.rule_mode(violation.rule_id)
    if mode == "block":
        _deny(violation.message())
    elif mode == "warn":
        _note(violation.message())
    return 0


def handle_post_tool_use(event: dict) -> int:
    """Record the write in the hash ledger."""
    target = _written_path(event)
    if target is None:
        return 0

    root = _root_for(event, hint=target)
    if root is None:
        return 0

    settings = config.load(root)
    if not settings.ledger:
        return 0

    ledger.record_write(
        root,
        target,
        {
            "session_id": event.get("session_id"),
            "agent_type": event.get("agent_type"),
        },
    )
    # The template-contract check (M4) reports through this same handler.
    return 0


def handle_subagent_stop(event: dict) -> int:
    """Agent-run trail. Inert until M4."""
    return 0


def handle_session_start(event: dict) -> int:
    """Report artifacts that changed outside the loop, if any."""
    root = _root_for(event)
    if root is None:
        return 0

    settings = config.load(root)
    if not settings.drift_check:
        return 0

    notice = drift.format_notice(drift.find_drifted(root))
    if notice:
        # Plain stdout on SessionStart is added to the session's context.
        sys.stdout.write(notice + "\n")
    return 0


HANDLERS = {
    "pre-tool-use": handle_pre_tool_use,
    "post-tool-use": handle_post_tool_use,
    "subagent-stop": handle_subagent_stop,
    "session-start": handle_session_start,
}


# --- scan (not a hook) ------------------------------------------------------


def _scan(argv: list[str]) -> int:
    """Read-only view of what the guard sees, for checking an install by hand."""
    start = Path(argv[0]) if argv else Path.cwd()
    root = artifacts.find_spark_root(start)
    if root is None:
        print(f"no .spark/ directory at or above {start} — the guard stays silent here")
        return 0

    settings = config.load(root)
    tracked = list(artifacts.iter_artifacts(root))
    entries = list(ledger.read_entries(root))
    drifted = drift.find_drifted(root)

    print(f"root:            {root}")
    print(f"enabled:         {settings.enabled} (ledger={settings.ledger}, drift={settings.drift_check})")
    print(f"artifacts:       {len(tracked)}")
    print(f"ledger entries:  {len(entries)}")
    print(f"drifted:         {len(drifted)}")
    for path in drifted:
        print(f"  ! {path}")
    print("rules:")
    for rule_id in (rules.R_PLAN, rules.R_QA, rules.R_RELEASE):
        print(f"  {settings.rule_mode(rule_id):<6} {rule_id}")
    return 0


def _check(argv: list[str]) -> int:
    """Replay the gate rules over every gated artifact already on disk.

    This is the dogfood harness: on a project whose features ran cleanly, it must
    print nothing. Every line it does print on such a project is a false positive.
    Read-only — it evaluates, it never writes.
    """
    start = Path(argv[0]) if argv else Path.cwd()
    root = artifacts.find_spark_root(start)
    if root is None:
        print(f"no .spark/ directory at or above {start}")
        return 0

    gated = (rules.PLAN, rules.QA, rules.RELEASE)
    checked = 0
    violations = 0

    spark = Path(root) / artifacts.SPARK_DIR
    for feature_dir in sorted(p for p in spark.iterdir() if p.is_dir()):
        if feature_dir.name == artifacts.GUARD_DIR:
            continue
        for name in gated:
            target = feature_dir / name
            if not target.is_file():
                continue
            checked += 1
            violation = rules.evaluate(root, target)
            if violation is not None:
                violations += 1
                print(f"{feature_dir.name}/{name}: [{violation.rule_id}] {violation.state}")

    print(f"checked {checked} gated artifacts, {violations} would be blocked")
    return 0


def main(argv: list[str], stream=None) -> int:
    """Never raises, never returns non-zero. See the fail-open rule above."""
    try:
        if not argv:
            return 0
        command, rest = argv[0], argv[1:]

        if command == "scan":
            return _scan(rest)
        if command == "check":
            return _check(rest)

        handler = HANDLERS.get(command)
        if handler is None:
            return 0

        event = _read_event(stream if stream is not None else sys.stdin)
        return handler(event)
    except Exception:  # noqa: BLE001 — fail-open is the whole point
        return 0
