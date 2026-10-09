from hermes_office.config import Settings
from hermes_office.redact import Pseudonymiser
from hermes_office.state import (
    STATE_ACTIVE,
    STATE_COMPLETED,
    STATE_IDLE,
    STATE_STALE,
    adapt_row,
    derive_activity,
    derive_state,
    origin_bucket,
)

NOW = 1_000_000.0


def settings():
    return Settings(active_window_s=120, idle_window_s=900)


def row(**kw):
    base = {
        "id": "raw-session",
        "source": "api_server",
        "started_at": NOW - 500,
        "last_active": NOW - 5,
        "ended_at": None,
        "message_count": 10,
        "tool_call_count": 4,
        "parent_session_id": None,
        "is_internal_child": False,
    }
    base.update(kw)
    return base


def test_state_active_when_recent():
    assert derive_state(row(last_active=NOW - 5), NOW, settings()) == STATE_ACTIVE


def test_state_idle_in_middle_window():
    assert derive_state(row(last_active=NOW - 300), NOW, settings()) == STATE_IDLE


def test_state_stale_when_long_silent():
    assert derive_state(row(last_active=NOW - 5000), NOW, settings()) == STATE_STALE


def test_state_completed_wins_over_recency():
    r = row(last_active=NOW - 1, ended_at=NOW - 1)
    assert derive_state(r, NOW, settings()) == STATE_COMPLETED


def test_activity_is_bounded_and_monotonic():
    assert derive_activity(0, 0) == 0.0
    assert 0.0 < derive_activity(3, 2) < 1.0
    assert derive_activity(1000, 1000) == 1.0


def test_subagent_detected_via_parent():
    a = adapt_row(row(parent_session_id="parent-x"), NOW, settings(), Pseudonymiser())
    assert a.is_subagent is True
    assert a.zone == "meeting"
    assert a.parent.startswith("s-")


def test_subagent_detected_via_internal_child():
    a = adapt_row(row(is_internal_child=True), NOW, settings(), Pseudonymiser())
    assert a.is_subagent is True


def test_zone_by_state_for_non_subagent():
    p = Pseudonymiser()
    assert adapt_row(row(last_active=NOW - 2), NOW, settings(), p).zone == "desk"
    assert adapt_row(row(last_active=NOW - 400), NOW, settings(), p).zone == "lounge"
    assert adapt_row(row(last_active=NOW - 9000), NOW, settings(), p).zone == "booth"
    assert adapt_row(row(ended_at=NOW - 1), NOW, settings(), p).zone == "exit"


def test_actor_has_no_sensitive_fields():
    a = adapt_row(row(parent_session_id="p"), NOW, settings(), Pseudonymiser())
    d = a.to_dict()
    for forbidden in ("title", "preview", "source", "parent_session_id", "model"):
        assert forbidden not in d


def test_origin_bucket():
    s = settings()
    assert origin_bucket("api_server", s) == "local"
    assert origin_bucket("telegram", s) == "remote"
    assert origin_bucket("a2a", s) == "agent"
    assert origin_bucket("", s) == "unknown"


def test_age_and_duration_are_non_negative():
    a = adapt_row(row(started_at=NOW + 100, last_active=NOW + 100), NOW, settings(), Pseudonymiser())
    assert a.age_sec == 0
    assert a.duration_sec == 0
