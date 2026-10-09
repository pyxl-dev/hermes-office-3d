"""Synthetic demo fixtures.

These rows are unmistakably fake: the source is ``"demo"`` and every id starts
with ``demo-``. They exist so the office can be run, screenshotted and tested
with no Hermes API and no secrets. They are never mixed with live data.
"""

from __future__ import annotations

import time


def demo_sessions(now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    # (id, source, age_of_last_activity_s, duration_s, tools, messages, ended, parent)
    specs = [
        ("demo-build", "demo", 2, 640, 27, 41, False, None),
        ("demo-research", "demo", 12, 380, 14, 22, False, None),
        ("demo-writer", "demo", 41, 900, 9, 30, False, None),
        ("demo-ops", "demo", 130, 1500, 6, 18, False, None),
        ("demo-child-a", "demo", 5, 90, 4, 8, False, "demo-build"),
        ("demo-child-b", "demo", 33, 70, 3, 6, False, "demo-build"),
        ("demo-lonely", "demo", 4000, 5000, 2, 4, False, None),
        ("demo-done", "demo", 900, 1200, 11, 20, True, None),
    ]
    rows = []
    for sid, source, age, dur, tools, messages, ended, parent in specs:
        row = {
            "id": sid,
            "source": source,
            "started_at": now - dur,
            "last_active": now - age,
            "ended_at": (now - age) if ended else None,
            "end_reason": "demo" if ended else None,
            "message_count": messages,
            "tool_call_count": tools,
            "api_call_count": tools,
            "parent_session_id": parent,
            "is_internal_child": False,
            "pinned": False,
            "archived": False,
            "hidden": False,
        }
        rows.append(row)
    return rows


def demo_health() -> dict:
    return {
        "api_server": {"active_runs": 2, "stored_runs": 3},
        "active_agents": 1,
        "gateway_busy": False,
        "version": "demo",
    }
