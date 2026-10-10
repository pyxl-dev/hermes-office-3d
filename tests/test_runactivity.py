"""Tests for the optional run-activity observer (synthetic fixtures only)."""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hermes_office.redact import Pseudonymiser  # noqa: E402
from hermes_office.runactivity import (  # noqa: E402
    RunActivityObserver,
    observe_or_empty,
)

SECRET_TOOL = "read_file"
SECRET_SESSION = "sess-REAL-IDENTIFIER-42"
SECRET_RUN = "run-REAL-IDENTIFIER-99"


def _write_log(tmp_path: Path, records: list[dict]) -> str:
    path = tmp_path / "activity.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return str(path)


def _record(*, ended_offset: float = 1.0, tool: str = SECRET_TOOL) -> dict:
    ended = time.time() - ended_offset
    return {
        "tool": tool,
        "status": "ok",
        "ok": True,
        "startedAt": ended - 0.5,
        "endedAt": ended,
        "outputSessionId": SECRET_SESSION,
        "outputRunId": SECRET_RUN,
        "instructionPreview": "SECRET PREVIEW TEXT",
        "traceId": "trace-SECRET",
    }


def test_unverified_bridge_call_is_never_working(tmp_path):
    """A logged bridge call is discovery, not proof of work."""
    obs = RunActivityObserver(_write_log(tmp_path, [_record(ended_offset=2.0)]), Pseudonymiser(b"salt"))
    out = obs.observe()
    assert len(out) == 1
    entry = next(iter(out.values()))
    assert entry["state"] == "recent"
    assert entry["category"] == "code"
    assert entry["age"] == "now"


def test_old_completion_is_not_working(tmp_path):
    obs = RunActivityObserver(_write_log(tmp_path, [_record(ended_offset=120.0)]), Pseudonymiser(b"salt"))
    entry = next(iter(obs.observe().values()))
    assert entry["state"] == "recent"
    assert entry["age"] in {"minutes", "minute"}


def test_stale_completion_is_dropped(tmp_path):
    obs = RunActivityObserver(_write_log(tmp_path, [_record(ended_offset=10_000.0)]), Pseudonymiser(b"salt"))
    assert obs.observe() == {}


def test_unknown_tool_maps_to_other(tmp_path):
    obs = RunActivityObserver(_write_log(tmp_path, [_record(tool="some_brand_new_tool")]), Pseudonymiser(b"salt"))
    assert next(iter(obs.observe().values()))["category"] == "other"


def test_pseudonym_is_stable_across_reads(tmp_path):
    path = _write_log(tmp_path, [_record()])
    first = set(RunActivityObserver(path, Pseudonymiser(b"salt")).observe())
    second = set(RunActivityObserver(path, Pseudonymiser(b"salt")).observe())
    assert first == second and len(first) == 1


def test_output_never_contains_identifiers_or_tool_names(tmp_path):
    obs = RunActivityObserver(_write_log(tmp_path, [_record(tool="terminal")]), Pseudonymiser(b"salt"))
    blob = json.dumps(obs.observe())
    for secret in (SECRET_SESSION, SECRET_RUN, "SECRET PREVIEW TEXT", "trace-SECRET"):
        assert secret not in blob
    assert set(json.loads(blob).popitem()[1]) == {"state", "category", "age"}


def test_malformed_lines_are_tolerated(tmp_path):
    path = tmp_path / "activity.jsonl"
    good = json.dumps(_record())
    path.write_text("not json\n{\"partial\":\n" + good + "\n", encoding="utf-8")
    out = RunActivityObserver(str(path), Pseudonymiser(b"salt")).observe()
    assert len(out) == 1


def test_missing_log_is_disabled_not_an_error(tmp_path):
    obs = RunActivityObserver(str(tmp_path / "nope.jsonl"), Pseudonymiser(b"salt"))
    assert obs.enabled() is False
    assert obs.observe() == {}


def test_empty_path_is_disabled():
    assert RunActivityObserver("", Pseudonymiser(b"salt")).enabled() is False


def test_observer_errors_never_break_the_payload():
    class Boom:
        def observe(self, now=None):
            raise RuntimeError("boom")

    assert observe_or_empty(Boom()) == {}
    assert observe_or_empty(None) == {}


def test_multiple_sessions_are_reported_independently(tmp_path):
    a = _record(ended_offset=1.0)
    b = _record(ended_offset=200.0)
    b["outputSessionId"] = "sess-OTHER-7"
    b["tool"] = "terminal"
    obs = RunActivityObserver(_write_log(tmp_path, [a, b]), Pseudonymiser(b"salt"))
    out = obs.observe()
    assert len(out) == 2
    # Neither is API-confirmed, so neither may claim to be working.
    assert sorted(e["state"] for e in out.values()) == ["recent", "recent"]


def test_latest_record_wins_for_a_session(tmp_path):
    old = _record(ended_offset=100.0, tool="terminal")
    new = _record(ended_offset=1.0, tool="read_file")
    obs = RunActivityObserver(_write_log(tmp_path, [old, new]), Pseudonymiser(b"salt"))
    entry = next(iter(obs.observe().values()))
    assert entry["category"] == "code", "the newest record decides the category"
    assert entry["state"] == "recent"


def test_running_run_without_api_confirmation_is_not_working(tmp_path):
    """Log status alone is not authoritative; the Runs API must confirm it."""
    rec = _record(ended_offset=90.0)
    rec["status"] = "running"
    rec["outputRunId"] = SECRET_RUN
    obs = RunActivityObserver(_write_log(tmp_path, [rec]), Pseudonymiser(b"salt"))
    assert next(iter(obs.observe().values()))["state"] == "recent"


def test_terminal_run_status_is_not_working(tmp_path):
    rec = _record(ended_offset=1.0)
    rec["status"] = "completed"
    rec["outputRunId"] = SECRET_RUN
    obs = RunActivityObserver(_write_log(tmp_path, [rec]), Pseudonymiser(b"salt"))
    assert next(iter(obs.observe().values()))["state"] == "recent"


def test_record_without_run_status_is_not_working(tmp_path):
    rec = _record(ended_offset=1.0)
    rec.pop("status", None)
    obs = RunActivityObserver(_write_log(tmp_path, [rec]), Pseudonymiser(b"salt"))
    assert next(iter(obs.observe().values()))["state"] == "recent"


def test_bridge_api_tools_never_claim_a_specific_category(tmp_path):
    """This log records bridge API calls, not the agent's internal tools, so it
    must not pretend to know the kind of work being done."""
    rec = _record(ended_offset=1.0, tool="get_hermes_run")
    rec["status"] = "running"
    rec["outputRunId"] = SECRET_RUN
    obs = RunActivityObserver(
        _write_log(tmp_path, [rec]), Pseudonymiser(b"salt"),
        resolve_run=lambda rid: {"session_id": "sess-CANONICAL-1", "status": "running"},
    )
    assert next(iter(obs.observe().values()))["category"] == "other"


def _running_record(offset=1.0):
    rec = _record(ended_offset=offset, tool="get_hermes_run")
    rec["status"] = "running"
    rec["outputRunId"] = SECRET_RUN
    return rec


def test_resolver_confirms_running_and_supplies_canonical_session(tmp_path):
    calls = []

    def resolve(run_id):
        calls.append(run_id)
        return {"session_id": "sess-CANONICAL-1", "status": "running"}

    obs = RunActivityObserver(_write_log(tmp_path, [_running_record()]), Pseudonymiser(b"salt"), resolve_run=resolve)
    entry = next(iter(obs.observe().values()))
    assert entry["state"] == "working"
    assert calls == [SECRET_RUN]


def test_resolver_terminal_status_downgrades_to_recent(tmp_path):
    obs = RunActivityObserver(
        _write_log(tmp_path, [_running_record()]),
        Pseudonymiser(b"salt"),
        resolve_run=lambda rid: {"session_id": "sess-CANONICAL-1", "status": "completed"},
    )
    assert next(iter(obs.observe().values()))["state"] == "recent"


def test_resolver_failure_does_not_claim_working(tmp_path):
    def boom(rid):
        raise RuntimeError("api down")

    obs = RunActivityObserver(_write_log(tmp_path, [_running_record()]), Pseudonymiser(b"salt"), resolve_run=boom)
    assert next(iter(obs.observe().values()))["state"] == "recent"


def test_resolver_is_cached_not_called_per_record(tmp_path):
    calls = []

    def resolve(run_id):
        calls.append(run_id)
        return {"session_id": "sess-CANONICAL-1", "status": "running"}

    records = [_running_record(offset=float(i)) for i in range(1, 6)]
    obs = RunActivityObserver(_write_log(tmp_path, records), Pseudonymiser(b"salt"), resolve_run=resolve)
    obs.observe()
    assert len(calls) == 1, "a repeatedly polled run must not be re-resolved every record"


def test_resolved_session_id_is_pseudonymised_never_raw(tmp_path):
    obs = RunActivityObserver(
        _write_log(tmp_path, [_running_record()]),
        Pseudonymiser(b"salt"),
        resolve_run=lambda rid: {"session_id": "sess-CANONICAL-1", "status": "running"},
    )
    blob = json.dumps(obs.observe())
    assert "sess-CANONICAL-1" not in blob and SECRET_RUN not in blob


def test_verified_run_activity_reaches_the_client_payload():
    """End-to-end: a confirmed running run must surface as a user-visible field
    on the matching actor, and only on that actor."""
    from hermes_office.adapter import build_payload
    from hermes_office.config import Settings
    from test_adapter import _FakeClient

    pseudo = Pseudonymiser(b"salt")
    now = 1_000_000.0
    def row(sid, age):
        return {
            "id": sid, "source": "cli", "title": "secret title", "preview": "secret preview",
            "started_at": now - 600, "last_active": now - age, "ended_at": None,
            "message_count": 3, "tool_call_count": 2, "parent_session_id": None,
            "is_internal_child": False, "archived": False, "hidden": False,
        }

    rows = [row("S-WORK", 5), row("S-IDLE", 30)]
    settings = Settings(hermes_api_key="present", max_actors=48)
    activity = {pseudo("S-WORK"): {"state": "working", "category": "other", "age": "now"}}

    payload = build_payload(settings, client=_FakeClient(rows), now=now,
                            pseudonymiser=pseudo, run_activity=activity)

    by_id = {a["id"]: a for a in payload["actors"]}
    working = by_id[pseudo("S-WORK")]
    idle = by_id[pseudo("S-IDLE")]
    assert working["run_activity"] == {"state": "working", "category": "other", "age": "now"}
    assert "run_activity" not in idle, "activity must not bleed onto other sessions"

    blob = json.dumps(payload)
    for secret in ("S-WORK", "S-IDLE", "secret title", "secret preview"):
        assert secret not in blob


def test_no_activity_means_no_field_and_no_fake_working():
    from hermes_office.adapter import build_payload
    from hermes_office.config import Settings
    from test_adapter import _FakeClient

    now = 1_000_000.0
    rows = [{"id": "S1", "source": "cli", "started_at": now - 600, "last_active": now - 5,
             "ended_at": None, "message_count": 1, "tool_call_count": 0,
             "parent_session_id": None, "is_internal_child": False,
             "archived": False, "hidden": False}]
    payload = build_payload(Settings(hermes_api_key="present"), client=_FakeClient(rows),
                            now=now, run_activity={})
    assert "run_activity" not in json.dumps(payload)


def test_confirmation_without_session_id_is_not_working(tmp_path):
    """An active run that does not name its session cannot be attributed."""
    obs = RunActivityObserver(
        _write_log(tmp_path, [_running_record()]), Pseudonymiser(b"salt"),
        resolve_run=lambda rid: {"session_id": None, "status": "running"},
    )
    assert next(iter(obs.observe().values()))["state"] == "recent"


def test_timestamps_with_offset_and_z_are_parsed_correctly(tmp_path):
    """Offset handling must be exact: ignoring it shifts the age by hours."""
    from hermes_office.runactivity import _parse_ts

    base = 1_700_000_000.0
    utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(base))
    off = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(base)) + "+02:00"
    assert abs(_parse_ts(utc) - base) < 1
    assert abs(_parse_ts(off) - (base - 7200)) < 1, "a +02:00 timestamp is 2h earlier in UTC"
    assert _parse_ts("2026-01-01T00:00:00") is not None, "naive stamps are read as UTC"
    assert _parse_ts("not a date") is None
    assert _parse_ts(None) is None
    assert _parse_ts(1234.5) == 1234.5


def test_env_key_is_actually_loaded_by_from_env(monkeypatch):
    """A config field that from_env ignores leaves the feature dead in deploy."""
    from hermes_office.config import Settings

    monkeypatch.setenv("HERMES_OFFICE_RUN_ACTIVITY_LOG", "/tmp/placeholder.jsonl")
    assert Settings.from_env().run_activity_log == "/tmp/placeholder.jsonl"
    monkeypatch.delenv("HERMES_OFFICE_RUN_ACTIVITY_LOG", raising=False)
    assert Settings.from_env().run_activity_log == ""


def test_resolver_attempts_are_capped_per_call(tmp_path):
    """The cap must bound outbound lookups, not merely the cache size."""
    calls = []

    def resolve(run_id):
        calls.append(run_id)
        return {"session_id": "sess-X", "status": "running"}

    records = []
    for i in range(10):
        rec = _record(ended_offset=1.0)
        rec["status"] = "running"
        rec["outputRunId"] = f"run-{i}"
        rec["outputSessionId"] = f"sess-{i}"
        records.append(rec)

    obs = RunActivityObserver(_write_log(tmp_path, records), Pseudonymiser(b"salt"),
                              resolve_run=resolve, max_resolutions=3)
    obs.observe()
    assert len(calls) <= 3, "one poll must not fire a request per record"


def test_worker_releases_terminal_runs(monkeypatch):
    """Without status awareness a finished run would hold a stream slot forever."""
    from hermes_office.runstream import RunStreamWorker, ToolEventTracker

    tracker = ToolEventTracker(Pseudonymiser(b"salt"))
    tracker.bind_run("run-Z", "sess-Z")
    tracker.handle("run-Z", {"event": "tool.started", "seq": 1, "tool": "read_file"})
    tracker.set_status("run-Z", "completed")
    assert tracker.snapshot() == {}
    worker = RunStreamWorker(tracker, "http://127.0.0.1:1", "k", status_check=lambda rid: "completed")
    assert worker.status_check("run-Z") == "completed"


def test_waiting_for_approval_is_not_execution():
    from hermes_office.runactivity import ACTIVE_RUN_STATUSES

    assert "waiting_for_approval" not in ACTIVE_RUN_STATUSES
    assert "stopping" in __import__("hermes_office.runactivity", fromlist=["x"]).TERMINAL_RUN_STATUSES


def test_working_run_is_not_overwritten_by_a_newer_finished_run(tmp_path):
    """A session with one live run and one just-finished run is still working."""
    live = _record(ended_offset=90.0)
    live["status"], live["outputRunId"] = "running", "run-live"
    done = _record(ended_offset=1.0)
    done["status"], done["outputRunId"] = "completed", "run-done"

    obs = RunActivityObserver(
        _write_log(tmp_path, [live, done]), Pseudonymiser(b"salt"),
        resolve_run=lambda rid: {"session_id": SECRET_SESSION,
                                 "status": "running" if rid == "run-live" else "completed"},
    )
    assert next(iter(obs.observe().values()))["state"] == "working"


def test_verified_working_session_survives_the_recency_filter():
    """A long quiet run that is genuinely executing must still have a character."""
    from hermes_office.adapter import build_payload
    from hermes_office.config import Settings
    from test_adapter import _FakeClient

    pseudo = Pseudonymiser(b"salt")
    now = 1_000_000.0
    row = {
        "id": "S-QUIET", "source": "cli", "started_at": now - 900,
        "last_active": now - 600,   # far outside the idle window
        "ended_at": None, "message_count": 2, "tool_call_count": 1,
        "parent_session_id": None, "is_internal_child": False,
        "archived": False, "hidden": False,
    }
    settings = Settings(hermes_api_key="present")

    dropped = build_payload(settings, client=_FakeClient([row]), now=now, pseudonymiser=pseudo)
    assert dropped["actors"] == [], "baseline: stale sessions are filtered out"

    kept = build_payload(settings, client=_FakeClient([row]), now=now, pseudonymiser=pseudo,
                         run_activity={pseudo("S-QUIET"): {"state": "working", "category": "other", "age": "now"}})
    assert [a["id"] for a in kept["actors"]] == [pseudo("S-QUIET")]
