"""Synthetic SSE tests for the run tool-event tracker (no network, no real data)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hermes_office.redact import Pseudonymiser  # noqa: E402
from hermes_office.runstream import (  # noqa: E402
    ToolEventTracker,
    category_for,
    parse_sse_frames,
    synthetic_tool_key,
)

SECRET_TOOL = "read_file"
SECRET_SESSION = "sess-REAL-77"
SECRET_RUN = "run-REAL-88"


def frame(seq, event, **fields):
    payload = {"event": event, "run_id": SECRET_RUN, "timestamp": 1.0, "seq": seq, **fields}
    return f"id: {seq}\ndata: {json.dumps(payload)}\n\n".encode()


def tracker(**kw):
    t = ToolEventTracker(Pseudonymiser(b"salt"), **kw)
    t.bind_run(SECRET_RUN, SECRET_SESSION)
    return t


def test_tool_start_marks_active_with_category():
    t = tracker()
    t.handle(SECRET_RUN, {"event": "tool.started", "seq": 1, "tool": SECRET_TOOL, "preview": "SECRET ARGS"})
    snap = t.snapshot()
    entry = next(iter(snap.values()))
    assert entry["tool_active"] is True
    assert entry["category"] == "code"


def test_tool_completed_clears_activity():
    t = tracker()
    t.handle(SECRET_RUN, {"event": "tool.started", "seq": 1, "tool": SECRET_TOOL})
    assert t.snapshot()
    t.handle(SECRET_RUN, {"event": "tool.completed", "seq": 2, "tool": SECRET_TOOL})
    assert t.snapshot() == {}


def test_no_start_means_no_activity():
    """A running run with no observed tool start must not look busy."""
    t = tracker()
    t.handle(SECRET_RUN, {"event": "message.delta", "seq": 1})
    assert t.snapshot() == {}


def test_replayed_and_out_of_order_frames_are_ignored():
    t = tracker()
    t.handle(SECRET_RUN, {"event": "tool.started", "seq": 5, "tool": SECRET_TOOL})
    first = t.snapshot()
    t.handle(SECRET_RUN, {"event": "tool.started", "seq": 5, "tool": "terminal"})
    t.handle(SECRET_RUN, {"event": "tool.started", "seq": 2, "tool": "terminal"})
    assert t.snapshot() == first, "replay/out-of-order must not change state"


def test_last_seq_tracks_cursor_for_reconnect():
    t = tracker()
    t.handle(SECRET_RUN, {"event": "tool.started", "seq": 7, "tool": SECRET_TOOL})
    assert t.last_seq(SECRET_RUN) == 7


def test_terminal_status_clears_active_tools():
    t = tracker()
    t.handle(SECRET_RUN, {"event": "tool.started", "seq": 1, "tool": SECRET_TOOL})
    t.set_status(SECRET_RUN, "completed")
    assert t.snapshot() == {}, "no stale typing after a run ends"


def test_run_stopping_event_clears_activity():
    t = tracker()
    t.handle(SECRET_RUN, {"event": "tool.started", "seq": 1, "tool": SECRET_TOOL})
    t.handle(SECRET_RUN, {"event": "run.stopping", "seq": 2})
    assert t.snapshot() == {}


def test_concurrent_runs_are_tracked_independently():
    t = ToolEventTracker(Pseudonymiser(b"salt"))
    t.bind_run("run-A", "sess-A")
    t.bind_run("run-B", "sess-B")
    t.handle("run-A", {"event": "tool.started", "seq": 1, "tool": "read_file"})
    t.handle("run-B", {"event": "tool.started", "seq": 1, "tool": "terminal"})
    snap = t.snapshot()
    assert len(snap) == 2
    assert sorted(e["category"] for e in snap.values()) == ["code", "terminal"]


def test_unbound_run_emits_nothing():
    """No verified session -> nothing on the wire, even with a live tool."""
    t = ToolEventTracker(Pseudonymiser(b"salt"))
    t.handle("run-X", {"event": "tool.started", "seq": 1, "tool": SECRET_TOOL})
    assert t.snapshot() == {}


def test_active_tools_are_bounded():
    t = tracker(max_tools_per_run=3)
    for seq in range(1, 20):
        t.handle(SECRET_RUN, {"event": "tool.started", "seq": seq, "tool": SECRET_TOOL})
    assert len(t._active[SECRET_RUN]) <= 3


def test_unknown_tool_is_other():
    assert category_for("brand_new_tool") == "other"
    assert category_for(None) == "other"


def test_snapshot_never_leaks_identifiers_or_tool_names():
    t = tracker()
    t.handle(SECRET_RUN, {"event": "tool.started", "seq": 1, "tool": SECRET_TOOL, "preview": "SECRET ARGS"})
    blob = json.dumps(t.snapshot())
    for secret in (SECRET_RUN, SECRET_SESSION, SECRET_TOOL, "SECRET ARGS"):
        assert secret not in blob
    entry = next(iter(t.snapshot().values()))
    assert set(entry) == {"tool_active", "tool_id", "category"}


def test_synthetic_key_is_stable_and_not_the_tool_name():
    a = synthetic_tool_key("run-A", 1, SECRET_TOOL)
    b = synthetic_tool_key("run-A", 1, SECRET_TOOL)
    c = synthetic_tool_key("run-A", 2, SECRET_TOOL)
    assert a == b and a != c and SECRET_TOOL not in a


def test_parse_sse_frames_handles_frames_comments_and_garbage():
    stream = [
        b": open\n\n",
        frame(1, "tool.started", tool=SECRET_TOOL),
        b"data: not-json\n\n",
        b"id: 2\ndata: " + json.dumps({"event": "tool.completed", "seq": 2}).encode() + b"\n\n",
    ]
    payloads = list(parse_sse_frames(stream))
    assert [p["seq"] for p in payloads] == [1, 2]


def test_parse_sse_frames_survives_split_chunks():
    whole = frame(3, "tool.started", tool=SECRET_TOOL)
    payloads = list(parse_sse_frames([whole[:10], whole[10:]]))
    assert len(payloads) == 1 and payloads[0]["seq"] == 3


def test_forget_run_releases_state():
    t = tracker()
    t.handle(SECRET_RUN, {"event": "tool.started", "seq": 1, "tool": SECRET_TOOL})
    t.forget_run(SECRET_RUN)
    assert t.snapshot() == {} and t.last_seq(SECRET_RUN) == -1
