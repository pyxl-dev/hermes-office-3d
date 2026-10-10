"""Turn observable session data into the sanitized office payload.

Public entry point: :func:`build_payload`. The result is the exact JSON the
browser receives and is deliberately small — no ids, no titles, no transcripts,
no paths, no model or channel names, no costs.
"""

from __future__ import annotations

import time

from .config import Settings
from .fixtures import demo_health, demo_sessions
from .hermes_client import HermesClient
from .redact import Pseudonymiser, scrub_actor
from .state import STATE_ACTIVE, STATE_COMPLETED, STATE_IDLE, STATE_STALE, Actor, adapt_row, rank_key

CAPABILITY_NOTES = [
    "Only recently active persisted sessions appear; older and completed sessions stay hidden.",
    "Subagent characters come from child session rows (parent_session_id / "
    "is_internal_child). If your build does not persist child rows for "
    "delegated work, subagents will not appear — we do not fake them.",
    "Session activity is inferred from last_active timestamps, not proof of an "
    "ongoing run; tool/message counts are historical totals.",
    "Titles, previews, prompts, transcripts, ids and paths are never sent to "
    "the browser.",
]


def _with_run_activity(actor: dict, run_activity: dict | None) -> dict:
    """Attach verified run activity, keyed by pseudonym. Never adds raw ids.

    Only the coarse enum reaches the client: a session is "working" solely when a
    run was observed executing, otherwise the observer's recency verdict stands.
    """
    if not run_activity:
        return actor
    entry = run_activity.get(str(actor.get("id")))
    if not isinstance(entry, dict):
        return actor
    merged = dict(actor)
    activity = {
        "state": entry.get("state"),
        "category": entry.get("category"),
        "age": entry.get("age"),
    }
    # A verified tool event refines this: it is the only thing allowed to make a
    # character look like it is actively working on something.
    if entry.get("tool_active"):
        activity["tool_active"] = True
        activity["tool_id"] = entry.get("tool_id")
        activity["category"] = entry.get("category")
    merged["run_activity"] = activity
    return merged


def _summarize(actors: list[Actor]) -> dict:
    by_state = {}
    for a in actors:
        by_state[a.state] = by_state.get(a.state, 0) + 1
    return {
        "sessions": len(actors),
        "active": by_state.get(STATE_ACTIVE, 0),
        "idle": by_state.get(STATE_IDLE, 0),
        "stale": by_state.get(STATE_STALE, 0),
        "completed": by_state.get(STATE_COMPLETED, 0),
        "subagents": sum(1 for a in actors if a.is_subagent),
    }


def _gateway_summary(health: dict | None) -> dict:
    if not isinstance(health, dict):
        return {"available": False}
    api = health.get("api_server") if isinstance(health.get("api_server"), dict) else {}
    return {
        "available": True,
        "active_runs": int(api.get("active_runs") or 0),
        "stored_runs": int(api.get("stored_runs") or 0),
        "active_agents": int(health.get("active_agents") or 0),
        "busy": bool(health.get("gateway_busy")),
        "version": str(health.get("version") or ""),
    }


def build_payload(
    settings: Settings,
    *,
    client: HermesClient | None = None,
    now: float | None = None,
    pseudonymiser: Pseudonymiser | None = None,
    run_activity: dict | None = None,
) -> dict:
    """Return the sanitized office payload.

    Falls back to synthetic fixtures when no Hermes API key is configured (demo
    mode) or when the live API cannot be reached.
    """
    now = time.time() if now is None else now
    pseudo = pseudonymiser or Pseudonymiser()

    mode = "demo"
    rows = None
    health = None
    degraded = False

    if not settings.demo_mode:
        client = client or HermesClient(settings)
        rows = client.fetch_sessions(limit=200)
        health = client.fetch_health()
        if rows is None:
            degraded = True  # live configured but unreachable -> stay honest
            rows = []
        mode = "live"

    if rows is None:
        rows = demo_sessions(now)
        health = demo_health()

    # Only live, non-archived, non-hidden rows become characters.
    filtered = [
        r
        for r in rows
        if not r.get("archived") and not r.get("hidden")
    ]

    # A persisted session is not a currently running worker. Old rows must
    # never become idle-looking NPCs that fill the office forever. Only recent
    # activity is visible; both ended and stale sessions are excluded.
    recent = [
        actor for actor in (adapt_row(r, now, settings, pseudo) for r in filtered)
        if actor.state in (STATE_ACTIVE, STATE_IDLE)
    ]
    recent.sort(key=rank_key)
    actors = recent[:settings.max_actors]

    cap = {
        "subagents": any(a.is_subagent for a in actors) or mode == "demo",
        "runs_detail": False,
        "transcripts": False,
    }

    return {
        "mode": mode,
        "degraded": degraded,
        "generated_at": now,
        "summary": _summarize(actors),
        "gateway": _gateway_summary(health),
        "capabilities": cap,
        "notes": CAPABILITY_NOTES,
        "actors": [_with_run_activity(scrub_actor(a.to_dict()), run_activity) for a in actors],
    }
