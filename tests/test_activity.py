"""The live activity log (activity-trail): session state and subagent runs."""

import json
import re
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from support import FIXTURES, GuardTestCase

PAYLOADS = FIXTURES / "payloads"

TS_MS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def payload(name: str, root: Path, **extra) -> dict:
    """A payload recorded in the T1 hook spike, with this test's repo substituted in."""
    raw = (PAYLOADS / name).read_text(encoding="utf-8").replace("__ROOT__", str(root))
    data = json.loads(raw)
    data.update(extra)
    return data


class ActivityTestCase(GuardTestCase):
    def setUp(self):
        super().setUp()
        self.make_spark_project()

    @property
    def activity_file(self) -> Path:
        return self.root / ".spark" / ".guard" / "activity.jsonl"

    def activity_entries(self) -> list[dict]:
        if not self.activity_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.activity_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def hook(self, command: str, fixture: str, **extra) -> tuple[int, str]:
        return self.run_hook(command, payload(fixture, self.root, **extra))


class TestSessionState(ActivityTestCase):
    def test_a_prompt_marks_the_session_busy(self):
        code, out = self.hook("user-prompt-submit", "user_prompt_submit.json")

        self.assertEqual((code, out), (0, ""))
        [entry] = self.activity_entries()
        self.assertEqual(entry["event"], "session_state")
        self.assertEqual((entry["state"], entry["reason"]), ("busy", "prompt"))
        self.assertEqual(entry["session_id"], "abc123")

    def test_a_finished_turn_marks_the_session_idle(self):
        code, out = self.hook("stop", "stop.json")

        self.assertEqual((code, out), (0, ""))
        [entry] = self.activity_entries()
        self.assertEqual((entry["state"], entry["reason"]), ("idle", "stop"))

    def test_every_line_carries_version_timestamp_event_and_session(self):
        self.hook("user-prompt-submit", "user_prompt_submit.json")
        self.hook("stop", "stop.json")

        for entry in self.activity_entries():
            with self.subTest(entry=entry):
                self.assertEqual(entry["v"], 1)
                self.assertRegex(entry["ts"], TS_MS)
                self.assertIn("event", entry)
                self.assertIn("session_id", entry)

    def test_lines_are_written_in_the_ledgers_sorted_key_form(self):
        self.hook("user-prompt-submit", "user_prompt_submit.json")
        line = self.activity_file.read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(line, json.dumps(json.loads(line), ensure_ascii=False, sort_keys=True))

    def test_a_missing_session_id_is_recorded_as_null(self):
        data = payload("stop.json", self.root)
        del data["session_id"]
        self.run_hook("stop", data)
        [entry] = self.activity_entries()
        self.assertIsNone(entry["session_id"])


class TestWaitingAndEnded(ActivityTestCase):
    def test_a_permission_dialog_marks_the_session_waiting(self):
        code, out = self.hook("permission-request", "permission_request.json")

        self.assertEqual((code, out), (0, ""), "the guard never decides a permission")
        [entry] = self.activity_entries()
        self.assertEqual((entry["state"], entry["reason"]), ("waiting", "permission"))

    def test_the_tool_input_of_the_request_is_not_recorded(self):
        self.hook("permission-request", "permission_request.json")
        text = self.activity_file.read_text(encoding="utf-8")
        for marker in ("TOOL_COMMAND", "TOOL_DESCRIPTION", "Bash", "addRules"):
            self.assertNotIn(marker, text)

    def test_the_next_event_supersedes_waiting(self):
        self.hook("permission-request", "permission_request.json")
        self.hook("stop", "stop.json")
        states = [e["state"] for e in self.activity_entries()]
        self.assertEqual(states, ["waiting", "idle"])

    def test_session_end_records_the_allowlisted_reason(self):
        for reason in ("clear", "prompt_input_exit", "logout", "other"):
            with self.subTest(reason=reason):
                self.hook("session-end", "session_end.json", reason=reason)
                entry = self.activity_entries()[-1]
                self.assertEqual((entry["state"], entry["reason"]), ("ended", reason))

    def test_an_unknown_end_reason_is_recorded_as_other(self):
        for reason in ("resume", "SECRET_REASON", "", 7, None):
            with self.subTest(reason=reason):
                self.hook("session-end", "session_end.json", reason=reason)
                self.assertEqual(self.activity_entries()[-1]["reason"], "other")
        self.assertNotIn("SECRET_REASON", self.activity_file.read_text(encoding="utf-8"))

    def test_two_sessions_interleave_and_filter_cleanly(self):
        sequence = [
            ("user-prompt-submit", "user_prompt_submit.json", "s1"),
            ("user-prompt-submit", "user_prompt_submit.json", "s2"),
            ("permission-request", "permission_request.json", "s1"),
            ("stop", "stop.json", "s2"),
            ("stop", "stop.json", "s1"),
            ("session-end", "session_end.json", "s2"),
        ]
        for command, fixture, sid in sequence:
            self.hook(command, fixture, session_id=sid)

        by_session = {}
        for entry in self.activity_entries():
            by_session.setdefault(entry["session_id"], []).append(entry["state"])
        self.assertEqual(by_session["s1"], ["busy", "waiting", "idle"])
        self.assertEqual(by_session["s2"], ["busy", "idle", "ended"])

    def test_a_killed_session_gets_nothing_written_on_its_behalf(self):
        # s1 goes quiet without an end; s2 starts, works and ends.
        self.hook("user-prompt-submit", "user_prompt_submit.json", session_id="s1")
        for command, fixture in (("user-prompt-submit", "user_prompt_submit.json"),
                                 ("stop", "stop.json"), ("session-end", "session_end.json")):
            self.hook(command, fixture, session_id="s2")

        s1 = [e for e in self.activity_entries() if e["session_id"] == "s1"]
        self.assertEqual([e["state"] for e in s1], ["busy"], "its last line stays its last")
        states = {e["state"] for e in self.activity_entries()}
        self.assertNotIn("abandoned", states)


class TestSubagentStart(ActivityTestCase):
    def test_a_start_is_recorded_with_id_type_and_feature(self):
        spec = self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_approved.md")
        self.post_tool_use(spec, session_id="abc123")

        code, out = self.hook("subagent-start", "subagent_start.json")

        self.assertEqual((code, out), (0, ""))
        [entry] = self.activity_entries()
        self.assertEqual(entry["event"], "subagent_start")
        self.assertEqual(entry["agent_id"], "a26e028603b8b4f58")
        self.assertEqual(entry["agent_type"], "aspark:product-owner")
        self.assertEqual(entry["feature"], "weekly-stats")

    def test_the_feature_is_the_one_the_trail_would_infer(self):
        from aspark_guard import trail

        spec = self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_approved.md")
        self.post_tool_use(spec, session_id="abc123")
        self.hook("subagent-start", "subagent_start.json")
        self.assertEqual(self.activity_entries()[0]["feature"],
                         trail.feature_for_session(self.root, "abc123"))

    def test_the_feature_is_null_before_the_session_wrote_anything(self):
        self.hook("subagent-start", "subagent_start.json")
        self.assertIsNone(self.activity_entries()[0]["feature"])

    def test_a_harness_internal_agent_is_not_recorded(self):
        self.hook("subagent-start", "subagent_start.json", agent_type="")
        self.assertEqual(self.activity_entries(), [])

    def test_an_ended_session_leaves_an_open_start_as_it_is(self):
        self.hook("subagent-start", "subagent_start.json")
        self.hook("session-end", "session_end.json")
        events = [e["event"] for e in self.activity_entries()]
        self.assertEqual(events, ["subagent_start", "session_state"], "no synthetic finish")


class TestAgentRun(ActivityTestCase):
    def start(self, agent_id="a1", **extra):
        return self.hook("subagent-start", "subagent_start.json", agent_id=agent_id, **extra)

    def stop(self, agent_id="a1", **extra):
        return self.run_hook("subagent-stop", {
            "session_id": "abc123", "cwd": str(self.root), "hook_event_name": "SubagentStop",
            "agent_id": agent_id, "agent_type": "aspark:product-owner", **extra,
        })

    def timed_stop(self, agent_id="a1") -> float:
        """Stop the run and return the real gap, in ms, since its start line's `ts`.

        The reference is measured, not the planned sleep: on a loaded machine a
        sleep overshoots, and AC-2.2 is about the gap between the two events.
        """
        starts = [e for e in self.activity_entries()
                  if e["event"] == "subagent_start" and e["agent_id"] == agent_id]
        started = datetime.strptime(starts[-1]["ts"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc)
        before = datetime.now(timezone.utc)
        self.stop(agent_id)
        return (before - started).total_seconds() * 1000

    def runs(self) -> list[dict]:
        return [e for e in self.activity_entries() if e["event"] == "agent_run"]

    def test_the_duration_matches_the_gap_between_start_and_stop(self):
        self.start()
        time.sleep(0.3)
        gap = self.timed_stop()

        [run] = self.runs()
        self.assertEqual((run["agent_id"], run["agent_type"]), ("a1", "aspark:product-owner"))
        self.assertGreaterEqual(gap, 300)
        self.assertAlmostEqual(run["duration_ms"], gap, delta=50)

    def test_a_stop_writes_nothing_to_stdout(self):
        self.start()
        self.assertEqual(self.stop(), (0, ""))

    def test_a_resumed_agent_measures_only_its_latest_run(self):
        self.start()
        time.sleep(0.4)
        first_gap = self.timed_stop()
        self.start()
        time.sleep(0.1)
        second_gap = self.timed_stop()

        first, second = self.runs()
        self.assertAlmostEqual(first["duration_ms"], first_gap, delta=50)
        self.assertAlmostEqual(second["duration_ms"], second_gap, delta=50)
        self.assertLess(second["duration_ms"], first["duration_ms"])

    def test_parallel_runs_of_one_type_pair_by_agent_id(self):
        self.start("a1")
        time.sleep(0.2)
        self.start("a2")
        gap_a2 = self.timed_stop("a2")
        gap_a1 = self.timed_stop("a1")
        durations = {r["agent_id"]: r["duration_ms"] for r in self.runs()}
        self.assertAlmostEqual(durations["a2"], gap_a2, delta=50)
        self.assertAlmostEqual(durations["a1"], gap_a1, delta=50)
        self.assertGreater(durations["a1"], durations["a2"])

    def test_a_start_in_the_rotated_file_still_pairs(self):
        from aspark_guard import activity

        started = datetime.now(timezone.utc) - timedelta(milliseconds=250)
        ts = started.strftime("%Y-%m-%dT%H:%M:%S.") + f"{started.microsecond // 1000:03d}Z"
        rotated = activity.rotated_path(self.root)
        rotated.parent.mkdir(parents=True)
        rotated.write_text(json.dumps({"v": 1, "ts": ts, "event": "subagent_start",
                                       "session_id": "abc123", "agent_id": "a1"}) + "\n")
        self.stop()
        self.assertAlmostEqual(self.runs()[0]["duration_ms"], 250, delta=50)

    def test_a_run_keeps_the_feature_its_start_was_given(self):
        # Review F1: the first run of a feature starts before any artifact exists,
        # then writes the spec. Its finish must not re-infer a different feature.
        self.start()
        spec = self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_draft.md")
        self.post_tool_use(spec, session_id="abc123")
        self.stop()

        [start] = [e for e in self.activity_entries() if e["event"] == "subagent_start"]
        [run] = self.runs()
        self.assertIsNone(start["feature"])
        self.assertEqual(run["feature"], start["feature"])

    def test_a_run_without_a_recorded_start_infers_its_feature(self):
        spec = self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_draft.md")
        self.post_tool_use(spec, session_id="abc123")
        self.stop()
        self.assertEqual(self.runs()[0]["feature"], "weekly-stats")

    def test_a_stop_without_a_recorded_start_has_no_duration(self):
        self.stop()
        self.assertIsNone(self.runs()[0]["duration_ms"])

    def test_a_start_of_another_session_does_not_pair(self):
        self.start(session_id="other")
        self.stop()
        self.assertIsNone(self.runs()[0]["duration_ms"])

    def test_no_stop_reason_is_recorded_even_when_the_payload_has_one(self):
        self.start()
        self.stop(stop_reason="end_turn")
        self.assertNotIn("stop_reason", self.runs()[0])

    def test_a_harness_internal_stop_writes_no_run(self):
        self.hook("subagent-stop", "subagent_stop_internal.json")
        self.assertEqual(self.runs(), [])

    def test_the_trail_still_writes_with_activity_off_and_the_other_way_round(self):
        trail_file = self.root / ".spark" / ".guard" / "trail.jsonl"

        self.write_config({"activity": False})
        self.stop()
        self.assertTrue(trail_file.exists())
        self.assertEqual(self.runs(), [])

        trail_file.unlink()
        self.write_config({"trail": False})
        self.stop()
        self.assertFalse(trail_file.exists())
        self.assertEqual(len(self.runs()), 1)


class TestDoubleStop(ActivityTestCase):
    """QA B4: one run, two SubagentStops, no start in between — the last stop wins."""

    AGENT = "a71b6de9de5cbd53e"

    def start(self, agent_id=AGENT):
        self.hook("subagent-start", "subagent_start.json", agent_id=agent_id,
                  agent_type="general-purpose")

    def stop(self, agent_id=AGENT):
        return self.hook("subagent-stop", "subagent_stop_double.json", agent_id=agent_id)

    def start_ts(self) -> datetime:
        starts = [e for e in self.activity_entries() if e["event"] == "subagent_start"]
        return datetime.strptime(starts[-1]["ts"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc)

    def timed_stop(self) -> float:
        started = self.start_ts()
        before = datetime.now(timezone.utc)
        self.assertEqual(self.stop(), (0, ""))
        return (before - started).total_seconds() * 1000

    def runs(self) -> list[dict]:
        return [e for e in self.activity_entries() if e["event"] == "agent_run"]

    def raw_lines(self) -> list[str]:
        return self.activity_file.read_text(encoding="utf-8").splitlines()

    def test_both_finishes_are_measured_from_the_same_start(self):
        self.start()
        time.sleep(0.1)
        first_gap = self.timed_stop()
        time.sleep(0.2)
        second_gap = self.timed_stop()

        first, second = self.runs()
        self.assertAlmostEqual(first["duration_ms"], first_gap, delta=50)
        self.assertAlmostEqual(second["duration_ms"], second_gap, delta=50)
        self.assertGreater(second["duration_ms"], first["duration_ms"])
        self.assertIsNotNone(second["duration_ms"])

    def test_the_first_line_is_left_as_it_was(self):
        self.start()
        self.stop()
        first_line = self.raw_lines()[-1]
        self.stop()
        self.assertEqual(self.raw_lines()[-2], first_line)

    def test_the_trail_gets_one_line_per_finish(self):
        trail_file = self.root / ".spark" / ".guard" / "trail.jsonl"
        self.start()
        self.stop()
        self.stop()
        self.assertEqual(len(trail_file.read_text(encoding="utf-8").splitlines()), 2)

    def test_two_finishes_without_a_start_both_have_no_duration(self):
        self.stop()
        self.stop()
        self.assertEqual([r["duration_ms"] for r in self.runs()], [None, None])

    def test_a_resume_after_a_double_stop_measures_from_its_own_start(self):
        self.start()
        time.sleep(0.3)
        self.stop()
        self.stop()
        self.start()
        gap = self.timed_stop()
        last = self.runs()[-1]
        self.assertAlmostEqual(last["duration_ms"], gap, delta=50)
        self.assertLess(last["duration_ms"], 250)

    def test_a_start_in_the_rotated_file_pairs_both_finishes(self):
        from aspark_guard import activity

        self.start()
        activity.activity_path(self.root).replace(activity.rotated_path(self.root))
        self.stop()
        self.stop()
        self.assertTrue(all(r["duration_ms"] is not None for r in self.runs()))
        self.assertEqual(len(self.runs()), 2)

    def test_a_resume_after_a_double_stop_takes_no_waiting_label(self):
        # Review F3 still holds: the resumed agent is `seen`, the new launch is not.
        self.start()
        self.stop()
        self.stop()
        data = payload("pre_tool_use_task.json", self.root)
        data["tool_input"].update(description="new launch", subagent_type="general-purpose")
        self.run_hook("pre-tool-use", data)
        self.start()
        self.start("a-new")
        starts = [e for e in self.activity_entries() if e["event"] == "subagent_start"]
        self.assertIsNone(starts[-2]["task"])
        self.assertEqual(starts[-1]["task"], "new launch")


class TestTaskLabel(ActivityTestCase):
    def launch(self, description="Write the spec", agent_type="aspark:product-owner", **extra):
        data = payload("pre_tool_use_task.json", self.root, **extra)
        data["tool_input"]["description"] = description
        data["tool_input"]["subagent_type"] = agent_type
        return self.run_hook("pre-tool-use", data)

    def start(self, agent_id="a1", agent_type="aspark:product-owner"):
        self.hook("subagent-start", "subagent_start.json", agent_id=agent_id, agent_type=agent_type)
        return [e for e in self.activity_entries() if e["event"] == "subagent_start"][-1]

    def test_the_launch_description_becomes_the_task(self):
        self.assertEqual(self.launch(), (0, ""), "the subagent tool is never gated")
        self.assertEqual(self.start()["task"], "Write the spec")

    def test_the_label_is_one_short_line_without_control_characters(self):
        self.launch("Review\nthe\x1b[31m diff \t" + "x" * 120)
        task = self.start()["task"]
        self.assertLessEqual(len(task), 80)
        self.assertTrue(task.startswith("Review the [31m diff x"))
        self.assertFalse(any(ord(ch) < 32 for ch in task))

    def test_no_description_gives_a_null_task(self):
        for value in (None, "", "   ", 7):
            with self.subTest(value=value):
                self.launch(value)
                self.assertIsNone(self.start()["task"])

    def test_a_start_without_a_launch_gets_a_null_task(self):
        self.assertIsNone(self.start()["task"])

    def test_two_parallel_launches_of_one_type_give_null_for_both(self):
        self.launch("run A")
        self.launch("run B")
        self.assertIsNone(self.start("a1")["task"])
        self.assertIsNone(self.start("a2")["task"])

    def test_launches_of_different_types_keep_their_own_label(self):
        self.launch("Write the spec", "aspark:product-owner")
        self.launch("Check the design", "aspark:designer")
        self.assertEqual(self.start("a2", "aspark:designer")["task"], "Check the design")
        self.assertEqual(self.start("a1", "aspark:product-owner")["task"], "Write the spec")

    def test_a_launch_older_than_60_seconds_is_ignored(self):
        from aspark_guard import activity

        self.launch("stale")
        pending = activity.pending_path(self.root)
        [entry] = [json.loads(l) for l in pending.read_text(encoding="utf-8").splitlines()]
        entry["t"] -= 61
        pending.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        self.assertIsNone(self.start()["task"])

    def test_paths_in_the_label_are_masked(self):
        # Review F2: the label is free text; a path would carry a user name into the log.
        home = str(Path.home())
        self.launch(f"Review {home}/proj/app.py, ~/notes.md and /etc/hosts via /peer-review")
        task = self.start()["task"]
        self.assertEqual(task, "Review <path> <path> and <path> via /peer-review")
        self.assertNotIn(home, task)

    def test_a_resumed_agent_does_not_take_a_waiting_launchs_label(self):
        # Review F3: a resume fires a start with no launch before it. A same-type
        # launch parked meanwhile belongs to the new agent, not to the resumed one.
        self.launch("first run")
        self.start("a1")
        self.stop_run("a1")
        self.launch("second agent")
        resumed = self.start("a1")
        fresh = self.start("a2")
        self.assertIsNone(resumed["task"])
        self.assertEqual(fresh["task"], "second agent")

    def stop_run(self, agent_id):
        self.run_hook("subagent-stop", {"session_id": "abc123", "cwd": str(self.root),
                                        "agent_id": agent_id, "agent_type": "aspark:product-owner"})

    def test_a_launch_of_another_session_is_not_used(self):
        self.launch(session_id="other")
        self.assertIsNone(self.start()["task"])

    def test_the_subagent_prompt_is_never_stored(self):
        self.launch()
        from aspark_guard import activity

        self.assertNotIn("SUBAGENT_PROMPT", activity.pending_path(self.root).read_text(encoding="utf-8"))

    def test_a_write_is_still_gated_as_before(self):
        self.write_fixture_artifact(".spark/weekly-stats/spec.md", "spec_draft.md")
        self.launch()
        code, out = self.run_hook("pre-tool-use", payload("pre_tool_use_write.json", self.root))
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_activity_off_parks_no_label(self):
        from aspark_guard import activity

        self.write_config({"activity": False})
        self.launch()
        self.assertFalse(activity.pending_path(self.root).exists())


class TestScan(ActivityTestCase):
    def scan(self) -> str:
        import io
        from contextlib import redirect_stdout

        from aspark_guard import cli

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["scan", str(self.root)])
        return buffer.getvalue()

    def test_scan_counts_current_and_rotated_lines_and_reports_the_size(self):
        from aspark_guard import activity

        self.hook("user-prompt-submit", "user_prompt_submit.json")
        self.hook("stop", "stop.json")
        rotated = activity.rotated_path(self.root)
        rotated.write_text('{"v": 1}\n{"v": 1}\n{"v": 1}\n', encoding="utf-8")
        size = self.activity_file.stat().st_size
        before = self.tree()

        out = self.scan()

        self.assertIn("activity lines:  5 (current + rotated)", out)
        self.assertIn(f"activity size:   {size} bytes", out)
        self.assertEqual(self.tree(), before, "scan is read-only")

    def test_scan_without_a_log_prints_zero_and_creates_nothing(self):
        before = self.tree()
        out = self.scan()
        self.assertIn("activity lines:  0", out)
        self.assertIn("activity size:   0 bytes", out)
        self.assertEqual(self.tree(), before)


class TestUntypedLaunch(ActivityTestCase):
    """QA B1: a launch without `subagent_type` still labels its start."""

    def launch(self, description, subagent_type=...):
        data = payload("pre_tool_use_task.json", self.root)
        data["tool_input"]["description"] = description
        if subagent_type is ...:
            del data["tool_input"]["subagent_type"]
        else:
            data["tool_input"]["subagent_type"] = subagent_type
        self.run_hook("pre-tool-use", data)

    def start(self, agent_id, agent_type="general-purpose"):
        self.hook("subagent-start", "subagent_start.json", agent_id=agent_id, agent_type=agent_type)
        return [e for e in self.activity_entries() if e["event"] == "subagent_start"][-1]

    def test_an_untyped_launch_labels_its_general_purpose_start(self):
        for missing in (..., "", None):
            with self.subTest(subagent_type=missing):
                self.launch("QA single omitted", missing)
                self.assertEqual(self.start(f"a-{missing!r}")["task"], "QA single omitted")

    def test_the_pending_entry_is_parked_as_general_purpose(self):
        from aspark_guard import activity

        self.launch("parked")
        [entry] = [json.loads(l) for l in
                   activity.pending_path(self.root).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(entry["agent_type"], "general-purpose")
        self.assertEqual(entry["task"], "parked")

    def test_an_untyped_and_an_explicit_general_purpose_launch_are_ambiguous(self):
        self.launch("one")
        self.launch("two", "general-purpose")
        self.assertIsNone(self.start("a1")["task"])
        self.assertIsNone(self.start("a2")["task"])

    def test_an_untyped_launch_is_never_claimed_by_another_type(self):
        self.launch("mine")
        self.assertIsNone(self.start("a1", "aspark:product-owner")["task"])
        self.assertEqual(self.start("a2")["task"], "mine")


class TestSwitch(ActivityTestCase):
    def test_activity_false_writes_nothing(self):
        self.write_config({"activity": False})
        self.hook("user-prompt-submit", "user_prompt_submit.json")
        self.hook("stop", "stop.json")
        self.assertFalse(self.activity_file.exists())

    def test_enabled_false_switches_activity_off_too(self):
        self.write_config({"enabled": False})
        self.hook("user-prompt-submit", "user_prompt_submit.json")
        self.assertFalse(self.activity_file.exists())

    def test_activity_is_on_by_default(self):
        self.hook("stop", "stop.json")
        self.assertTrue(self.activity_file.exists())


if __name__ == "__main__":
    unittest.main()
