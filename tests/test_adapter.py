import json

from hermes_office.adapter import build_payload
from hermes_office.config import Settings
from hermes_office.redact import FORBIDDEN_KEYS


def demo_settings():
    return Settings(hermes_api_key="", max_actors=48)


class _DeadClient:
    """A client whose upstream is unreachable."""

    def fetch_sessions(self, limit=200):
        return None

    def fetch_health(self):
        return None


class _FakeClient:
    def __init__(self, rows, health=None):
        self.rows = rows
        self.health = health

    def fetch_sessions(self, limit=200):
        return self.rows

    def fetch_health(self):
        return self.health


def _all_keys(obj):
    keys = set()
    if isinstance(obj, dict):
        keys |= set(obj.keys())
        for v in obj.values():
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            keys |= _all_keys(v)
    return keys


def test_demo_payload_shape():
    p = build_payload(demo_settings())
    assert p["mode"] == "demo"
    assert p["summary"]["sessions"] == len(p["actors"]) > 0
    assert p["capabilities"]["subagents"] is True
    assert isinstance(p["notes"], list) and p["notes"]


def test_demo_payload_has_no_forbidden_keys():
    p = build_payload(demo_settings())
    assert not (FORBIDDEN_KEYS & _all_keys(p))


def test_live_payload_never_leaks_title_or_preview():
    rows = [{
        "id": "secret-session-id",
        "source": "telegram",
        "title": "My private conversation about finances",
        "preview": "leaked preview text",
        "user_id": "example-user",
        "started_at": 1_000_000.0,
        "last_active": 1_000_010.0,
        "ended_at": None,
        "message_count": 6,
        "tool_call_count": 3,
        "parent_session_id": None,
        "is_internal_child": False,
        "archived": False,
        "hidden": False,
        "estimated_cost_usd": 1.23,
    }]
    s = Settings(hermes_api_key="present", max_actors=48)
    p = build_payload(s, client=_FakeClient(rows), now=1_000_020.0, pseudonymiser=None)
    blob = json.dumps(p)
    assert "secret-session-id" not in blob
    assert "finances" not in blob
    assert "leaked preview" not in blob
    assert "example-user" not in blob
    assert "1.23" not in blob
    assert p["mode"] == "live"
    assert len(p["actors"]) == 1
    assert p["actors"][0]["origin"] == "remote"


def test_archived_and_hidden_rows_are_excluded():
    rows = [
        {"id": "a", "archived": True, "last_active": 1_000_000.0, "started_at": 1_000_000.0},
        {"id": "b", "hidden": True, "last_active": 1_000_000.0, "started_at": 1_000_000.0},
        {"id": "c", "last_active": 1_000_000.0, "started_at": 1_000_000.0},
    ]
    s = Settings(hermes_api_key="present")
    p = build_payload(s, client=_FakeClient(rows), now=1_000_005.0)
    assert len(p["actors"]) == 1


def test_degraded_when_configured_but_unreachable():
    s = Settings(hermes_api_key="present")
    p = build_payload(s, client=_DeadClient(), now=1_000_000.0)
    assert p["mode"] == "live"
    assert p["degraded"] is True
    assert p["actors"] == []


def test_max_actors_cap_and_priority_ordering():
    now = 1_000_000.0
    historical = [
        {"id": f"old-{i}", "last_active": now - 90_000, "started_at": now - 90_000}
        for i in range(60)
    ]
    current = [
        {"id": f"fresh-{i}", "last_active": now - i, "started_at": now - 100}
        for i in range(15)
    ]
    s = Settings(hermes_api_key="present", max_actors=10)
    p = build_payload(s, client=_FakeClient(historical + current), now=now)
    assert len(p["actors"]) == 10
    assert p["summary"]["stale"] == 0
    assert all(a["state"] == "active" for a in p["actors"])


def test_historical_and_ended_sessions_never_spawn_characters():
    now = 1_000_000.0
    rows = [
        {"id": f"historical-{i}", "last_active": now - 86400, "started_at": now - 86400,
         "is_internal_child": i % 7 == 0}
        for i in range(48)
    ]
    rows.append({"id": "finished", "ended_at": now - 1, "last_active": now - 1,
                 "started_at": now - 60})
    health = {"api_server": {"active_runs": 1}, "gateway_busy": True, "active_agents": 1}
    p = build_payload(Settings(hermes_api_key="present"), client=_FakeClient(rows, health), now=now)
    assert p["actors"] == []
    assert p["summary"]["sessions"] == 0
    assert p["summary"]["stale"] == 0
    assert p["summary"]["completed"] == 0
    assert p["summary"]["subagents"] == 0
    # An aggregate busy flag does not identify a particular session. No fake worker.
    assert p["gateway"]["active_runs"] == 1
    assert p["gateway"]["busy"] is True


def test_recent_subagent_kept_without_exposing_parent_or_other_history():
    now = 1_000_000.0
    rows = [
        {"id": "old-parent-sensitive", "started_at": now - 86400, "last_active": now - 86400},
        {"id": "child-sensitive", "started_at": now - 20, "last_active": now - 5,
         "parent_session_id": "old-parent-sensitive", "is_internal_child": True},
    ]
    p = build_payload(Settings(hermes_api_key="present"), client=_FakeClient(rows), now=now)
    assert len(p["actors"]) == 1
    assert p["actors"][0]["is_subagent"]
    assert p["actors"][0]["parent"].startswith("s-")
    assert "old-parent-sensitive" not in json.dumps(p)
    assert "child-sensitive" not in json.dumps(p)


def test_pseudonyms_do_not_leak_raw_ids():
    rows = [{"id": "raw-id-xyz", "last_active": 1_000_000.0, "started_at": 1_000_000.0}]
    s = Settings(hermes_api_key="present")
    p = build_payload(s, client=_FakeClient(rows), now=1_000_000.0)
    assert "raw-id-xyz" not in json.dumps(p)
