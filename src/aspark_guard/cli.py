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
from datetime import datetime, timezone
from pathlib import Path

from . import activity, artifacts, config, drift, ledger, overrides, rules, templates, trail

EVENTS = (
    "pre-tool-use",
    "post-tool-use",
    "subagent-stop",
    "session-start",
    "user-prompt-submit",
    "stop",
    "permission-request",
    "session-end",
    "subagent-start",
)


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


def _note(context: str, event_name: str = "PreToolUse") -> None:
    """Allow, but put the finding in front of the model."""
    _emit({
        "hookSpecificOutput": {
            "hookEventName": event_name,
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
    if event.get("tool_name") == activity.SUBAGENT_TOOL:
        return _park_task_label(event)

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
    if mode == "off":
        return 0

    message = violation.message(_override_lines(root, violation))
    if mode == "block":
        _deny(message)
    else:
        _note(message)
    return 0


def _park_task_label(event: dict) -> int:
    """A subagent is about to launch: keep its short label for the SubagentStart.

    The subagent tool shares this hook with the gate, through a second matcher that
    calls the same command. It is never gated, and stdout stays empty.
    """
    root = _root_for(event)
    if root is None:
        return 0

    settings = config.load(root)
    if settings.activity:
        activity.record_pending_task(root, event)
    return 0


def _override_lines(root: Path, violation) -> list[str]:
    """Ready-to-paste override entries for whatever this block is about.

    For a gate rule that is the violation's own triggers. For R4 — an agent writing
    the override file — it is every gate currently blocking in that feature, which
    is what the human was presumably about to overrule.
    """
    timestamp = ledger.utc_now()
    feature = violation.feature
    if feature is None:
        return []

    if violation.rule_id == rules.R_OVERRIDE:
        pairs = [
            (pending.rule_id, trigger)
            for pending in rules.pending(root, feature)
            for trigger in rules.uncovered(root, pending)
        ]
    else:
        pairs = [(violation.rule_id, trigger) for trigger in violation.triggers]

    return [
        overrides.suggest_line(root, rule_id, trigger.artifact, trigger.sha256, timestamp)
        for rule_id, trigger in pairs
        if trigger.sha256
    ]


def handle_post_tool_use(event: dict) -> int:
    """Record the write in the hash ledger."""
    target = _written_path(event)
    if target is None:
        return 0

    root = _root_for(event, hint=target)
    if root is None:
        return 0

    settings = config.load(root)

    if settings.ledger:
        ledger.record_write(
            root,
            target,
            {
                "session_id": event.get("session_id"),
                "agent_type": event.get("agent_type"),
            },
        )

    if settings.template_check:
        findings = templates.check_file(target)
        if findings:
            rel = artifacts.relative_to_root(target, root) or str(target)
            _note(templates.format_findings(rel, findings), event_name="PostToolUse")
    return 0


def handle_subagent_stop(event: dict) -> int:
    """Record that a subagent finished, so agent runs can be counted from the repo."""
    stopped = datetime.now(timezone.utc)
    root = _root_for(event)
    if root is None:
        return 0

    settings = config.load(root)
    if settings.trail:
        trail.record_run(root, event)
    if settings.activity:
        activity.record_agent_run(root, event, stopped)
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


def _record_state(event: dict, state: str, reason: str) -> int:
    """Log a session's state. Writes nothing to stdout: on UserPromptSubmit plain
    output is added to the model's context, and the activity log must never be."""
    root = _root_for(event)
    if root is None:
        return 0

    settings = config.load(root)
    if settings.activity:
        activity.record_state(root, event, state, reason)
    return 0


def handle_user_prompt_submit(event: dict) -> int:
    """A prompt arrived — the user's, or one the harness delivers on its own."""
    return _record_state(event, "busy", "prompt")


def handle_stop(event: dict) -> int:
    """The main session finished its turn. Subagents still running are not ended here."""
    return _record_state(event, "idle", "stop")


def handle_permission_request(event: dict) -> int:
    """A permission dialog is up: Claude is waiting for the user.

    This hook can also decide the request; it never does. Empty stdout leaves the
    harness's own dialog exactly as it would be without the guard.
    """
    return _record_state(event, "waiting", "permission")


def handle_session_end(event: dict) -> int:
    """A clean end. A killed session gets no line at all — nothing is written for it."""
    return _record_state(event, "ended", activity.end_reason(event))


def handle_subagent_start(event: dict) -> int:
    """A subagent started, so the cockpit can show it running before it finishes."""
    root = _root_for(event)
    if root is None:
        return 0

    settings = config.load(root)
    if settings.activity:
        activity.record_subagent_start(root, event)
    return 0


HANDLERS = {
    "pre-tool-use": handle_pre_tool_use,
    "post-tool-use": handle_post_tool_use,
    "subagent-stop": handle_subagent_stop,
    "session-start": handle_session_start,
    "user-prompt-submit": handle_user_prompt_submit,
    "stop": handle_stop,
    "permission-request": handle_permission_request,
    "session-end": handle_session_end,
    "subagent-start": handle_subagent_start,
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
    runs = list(trail.read_entries(root))
    activity_lines = sum(1 for _ in activity.read_entries(root))
    try:
        activity_size = activity.activity_path(root).stat().st_size
    except OSError:
        activity_size = 0
    drifted = drift.find_drifted(root)
    contract = [
        (artifacts.relative_to_root(path, root), findings)
        for path in tracked
        for findings in [templates.check_file(path)]
        if findings
    ]

    print(f"root:            {root}")
    print(f"enabled:         {settings.enabled} (ledger={settings.ledger}, drift={settings.drift_check})")
    print(f"artifacts:       {len(tracked)}")
    print(f"ledger entries:  {len(entries)}")
    print(f"agent runs:      {len(runs)}")
    print(f"activity lines:  {activity_lines} (current + rotated)")
    print(f"activity size:   {activity_size} bytes (rotates at {activity.MAX_BYTES})")
    print(f"template drift:  {len(contract)} artifact(s)")
    for rel, findings in contract:
        for finding in findings:
            print(f"  ~ {rel}: {finding}")
    print(f"drifted:         {len(drifted)}")
    for path in drifted:
        print(f"  ! {path}")
    print("rules:")
    for rule_id in rules.ALL_RULES:
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

    checked = 0
    violations = 0
    overridden = 0

    spark = Path(root) / artifacts.SPARK_DIR
    for feature_dir in sorted(p for p in spark.iterdir() if p.is_dir()):
        if feature_dir.name == artifacts.GUARD_DIR:
            continue
        for name in rules.GATED_ARTIFACTS:
            target = feature_dir / name
            if not target.is_file():
                continue
            checked += 1

            raw = rules.evaluate(root, target, apply_overrides=False)
            if raw is None:
                continue

            violation = rules.evaluate(root, target)
            if violation is None:
                # Every trigger is accounted for by an override. Showing these is
                # the point of the mechanism: an override is meant to be seen.
                overridden += 1
                print(f"{feature_dir.name}/{name}: OVERRIDDEN [{raw.rule_id}] {raw.state}")
            else:
                violations += 1
                print(f"{feature_dir.name}/{name}: [{violation.rule_id}] {violation.state}")

    summary = f"checked {checked} gated artifacts, {violations} would be blocked"
    if overridden:
        summary += f", {overridden} overridden"
    print(summary)
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
