"""NFR-1 benchmark: wall time per hook invocation, as the harness pays it.

Not a test (`discover` only collects `test_*.py`). Run by hand:

    python3 tests/bench_hooks.py [runs] [python]            # per process, as the harness pays
    python3 tests/bench_hooks.py inproc [runs]              # the guard's own share, after import
    python3 tests/bench_hooks.py compare <other-repo> [runs] [python]
                                                            # gate hooks, this tree vs another, interleaved

Each hook is started as its own process with its payload on stdin — interpreter
startup included, because that is what every hook costs a session. A bare
`python -c pass` is measured alongside, so the guard's own share can be told apart
from the interpreter's. Three setups: a project with `.spark/`, one without, and one
whose activity log sits at the 2 MB rotation mark.
"""

from __future__ import annotations

import io
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD = REPO_ROOT / "bin" / "guard.py"
sys.path.insert(0, str(REPO_ROOT / "src"))

from aspark_guard import activity  # noqa: E402


def payloads(root: Path) -> dict[str, dict]:
    base = {"session_id": "bench", "cwd": str(root)}
    return {
        "user-prompt-submit": {**base, "prompt": "x"},
        "stop": base,
        "permission-request": {**base, "tool_name": "Bash", "tool_input": {"command": "x"}},
        "session-end": {**base, "reason": "clear"},
        "subagent-start": {**base, "agent_id": "a-bench", "agent_type": "aspark:reviewer"},
        "subagent-stop": {**base, "agent_id": "a-bench", "agent_type": "aspark:reviewer"},
        "pre-tool-use (Agent)": {**base, "tool_name": "Agent",
                                 "tool_input": {"description": "d", "subagent_type": "aspark:reviewer"}},
        "pre-tool-use (Write)": {**base, "tool_name": "Write",
                                 "tool_input": {"file_path": str(root / ".spark" / "f" / "plan.md")}},
        "post-tool-use (Write)": {**base, "tool_name": "Write",
                                  "tool_input": {"file_path": str(root / ".spark" / "f" / "spec.md")}},
    }


def time_run(argv: list[str], stdin: str) -> float:
    start = time.perf_counter()
    subprocess.run(argv, input=stdin, capture_output=True, text=True, check=False)
    return (time.perf_counter() - start) * 1000


def summarize(samples: list[float]) -> dict:
    ordered = sorted(samples)
    p95 = ordered[max(0, int(round(0.95 * len(ordered))) - 1)]
    return {"median": statistics.median(ordered), "p95": p95, "max": ordered[-1]}


def make_project(kind: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix=f"guard-bench-{kind}-"))
    if kind == "none":
        return root
    feature = root / ".spark" / "f"
    feature.mkdir(parents=True)
    (feature / "spec.md").write_text("| **Status** | `approved` |\n", encoding="utf-8")
    if kind == "cap":
        log = activity.activity_path(root)
        log.parent.mkdir(parents=True, exist_ok=True)
        # Just under the mark, with no line naming the bench agent: the stop's pairing
        # scan reads both files in full and every line fails the substring filter.
        line = json.dumps({"v": 1, "event": "session_state", "session_id": "other",
                           "pad": "x" * 150}) + "\n"
        rotated = activity.rotated_path(root)
        rotated.write_text(line * (activity.MAX_BYTES // len(line)), encoding="utf-8")
        log.write_text(line * (activity.MAX_BYTES // len(line) - 5), encoding="utf-8")
    return root


INPROC = ("user-prompt-submit", "stop", "permission-request", "session-end",
          "subagent-start", "subagent-stop", "pre-tool-use (Agent)")


def seed_realistic_cap(root: Path) -> None:
    """The 2 MB mark with real-shaped lines of other agents, and the bench agent's own
    start, run, run near the top of the rotated file — the stop's worst ordinary case."""
    line_of = lambda i: json.dumps({  # noqa: E731
        "v": 1, "ts": "2026-09-23T10:00:00.123Z", "event": "subagent_start",
        "session_id": "f3b41805-065f-49fd-9743-d310b76dd08d", "agent_id": f"a{i:016x}",
        "agent_type": "aspark:reviewer", "feature": "weekly-stats", "task": "Review the diff",
    }, sort_keys=True) + "\n"
    own = [json.dumps({"v": 1, "ts": "2026-09-23T09:59:59.000Z", "event": e,
                       "session_id": "bench", "agent_id": "a-bench"}, sort_keys=True) + "\n"
           for e in ("subagent_start", "agent_run", "agent_run")]
    per_file = activity.MAX_BYTES // len(line_of(0))
    rotated = activity.rotated_path(root)
    rotated.parent.mkdir(parents=True, exist_ok=True)
    rotated.write_text("".join(own) + "".join(line_of(i) for i in range(per_file - 3)),
                       encoding="utf-8")
    activity.activity_path(root).write_text(
        "".join(line_of(per_file + i) for i in range(per_file - 5)), encoding="utf-8")


def run_inproc(runs: int) -> int:
    from contextlib import redirect_stdout

    from aspark_guard import cli

    print(f"{runs} runs per row · in-process · {sys.executable} ({sys.version.split()[0]})\n")
    for kind in ("spark", "none", "cap"):
        root = make_project("spark" if kind == "cap" else kind)
        if kind == "cap":
            seed_realistic_cap(root)
        try:
            print(f"-- project: {kind}")
            for label in INPROC:
                payload = payloads(root)[label]
                command = label.split(" ")[0]
                samples = []
                for _ in range(runs):
                    stdin = io.StringIO(json.dumps(payload))
                    start = time.perf_counter()
                    with redirect_stdout(io.StringIO()):
                        cli.main([command], stdin)
                    samples.append((time.perf_counter() - start) * 1000)
                s = summarize(samples)
                print(f"  {label:<32} median {s['median']:6.1f}  p95 {s['p95']:6.1f}  "
                      f"max {s['max']:6.1f}  ms")
        finally:
            shutil.rmtree(root, ignore_errors=True)
        print()
    return 0


def run_compare(other: Path, runs: int, python: str) -> int:
    """The gate hooks of this tree and another, alternated so both share the load."""
    root = make_project("spark")
    guards = {"this": GUARD, "other": Path(other) / "bin" / "guard.py"}
    cases = {k: v for k, v in payloads(root).items() if k.endswith("(Write)")}
    samples = {}
    try:
        for _ in range(runs):
            for tag, guard in guards.items():
                for label, payload in cases.items():
                    samples.setdefault((label, tag), []).append(
                        time_run([python, str(guard), label.split(" ")[0]], json.dumps(payload)))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"{runs} alternating runs per row · {python} · other = {other}\n")
    for (label, tag), values in sorted(samples.items()):
        s = summarize(values)
        print(f"  {label:<24} {tag:<6} median {s['median']:6.1f}  p95 {s['p95']:6.1f}  "
              f"max {s['max']:6.1f}  ms")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "inproc":
        return run_inproc(int(sys.argv[2]) if len(sys.argv) > 2 else 50)
    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        return run_compare(Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 60,
                           sys.argv[4] if len(sys.argv) > 4 else "python3")
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    python = sys.argv[2] if len(sys.argv) > 2 else "python3"
    version = subprocess.run([python, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"{runs} runs per row · {python} ({version})\n")

    baseline = summarize([time_run([python, "-c", "pass"], "") for _ in range(runs)])
    print(f"{'bare interpreter start':<34} median {baseline['median']:6.1f}  "
          f"p95 {baseline['p95']:6.1f}  max {baseline['max']:6.1f}  ms\n")

    for kind in ("spark", "none", "cap"):
        root = make_project(kind)
        try:
            print(f"-- project: {kind}")
            for label, payload in payloads(root).items():
                command = label.split(" ")[0]
                stdin = json.dumps(payload)
                samples = [time_run([python, str(GUARD), command], stdin) for _ in range(runs)]
                s = summarize(samples)
                print(f"  {label:<32} median {s['median']:6.1f}  p95 {s['p95']:6.1f}  "
                      f"max {s['max']:6.1f}  ms")
        finally:
            shutil.rmtree(root, ignore_errors=True)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
