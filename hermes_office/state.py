"""Adapt observable Hermes session fields into an office character state.

The rule is simple: **states come only from data Hermes actually reports**
(``ended_at``, ``last_active``, ``tool_call_count``, ``message_count``,
``parent_session_id``). We never invent a "mood", a "meeting", a "tasks done"
number or any other fact the API does not expose. Zones are a presentation
choice; the ``state`` field is the honest one and is documented in the README.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from .config import Settings

# Observable state vocabulary.
STATE_ACTIVE = "active"        # recently active, not ended
STATE_IDLE = "idle"            # present but quiet
STATE_STALE = "stale"          # not ended, long silent
STATE_COMPLETED = "completed"  # has an ended_at

ALL_STATES = (STATE_ACTIVE, STATE_IDLE, STATE_STALE, STATE_COMPLETED)

# Zone assignment per state — where a character *stands*, not a claim about
# what it is doing.
ZONE_BY_STATE = {
    STATE_ACTIVE: "desk",
    STATE_IDLE: "lounge",
    STATE_STALE: "booth",
    STATE_COMPLETED: "exit",
}
ZONE_COLLAB = "meeting"  # used for subagents/children


def origin_bucket(source: object, settings: Settings) -> str:
    """Coarse origin: local operator / remote person / agent-to-agent."""
    s = str(source or "").lower()
    if s in settings.agent_sources:
        return "agent"
    if s in settings.local_sources:
        return "local"
    if not s:
        return "unknown"
    return "remote"


@dataclass
class Actor:
    id: str
    state: str
    zone: str
    origin: str
    is_subagent: bool
    parent: str
    age_sec: int
    duration_sec: int
    tools: int
    messages: int
    turns: int
    ended: bool
    activity: float  # 0..1, a plain function of observable counts

    def to_dict(self) -> dict:
        return asdict(self)


def _num(row: dict, key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def derive_state(row: dict, now: float, settings: Settings) -> str:
    if row.get("ended_at"):
        return STATE_COMPLETED
    last = row.get("last_active") or row.get("started_at")
    try:
        age = now - float(last)
    except (TypeError, ValueError):
        return STATE_STALE
    if age <= settings.active_window_s:
        return STATE_ACTIVE
    if age <= settings.idle_window_s:
        return STATE_IDLE
    return STATE_STALE


def derive_activity(tools: int, turns: int) -> float:
    """A bounded 0..1 signal from observable counts (log-ish saturation).

    Nothing random, nothing invented: more recorded tool calls / turns means a
    busier character, capped at 1.
    """
    import math

    raw = (tools + turns) / 12.0
    return round(min(1.0, math.log1p(raw) / math.log1p(12.0)) if raw else 0.0, 3)


def adapt_row(
    row: dict,
    now: float,
    settings: Settings,
    pseudonymise,
) -> Actor:
    """Build one :class:`Actor` from a raw session row."""
    state = derive_state(row, now, settings)
    is_child = bool(row.get("parent_session_id")) or bool(row.get("is_internal_child"))
    tools = _num(row, "tool_call_count")
    messages = _num(row, "message_count")
    turns = messages // 2

    zone = ZONE_COLLAB if is_child else ZONE_BY_STATE.get(state, "lounge")

    try:
        started = float(row.get("started_at") or now)
    except (TypeError, ValueError):
        started = now
    try:
        last = float(row.get("last_active") or started)
    except (TypeError, ValueError):
        last = started

    return Actor(
        id=pseudonymise(row.get("id")),
        state=state,
        zone=zone,
        origin=origin_bucket(row.get("source"), settings),
        is_subagent=is_child,
        parent=pseudonymise(row["parent_session_id"]) if row.get("parent_session_id") else "",
        age_sec=max(0, int(now - last)),
        duration_sec=max(0, int(now - started)),
        tools=tools,
        messages=messages,
        turns=turns,
        ended=bool(row.get("ended_at")),
        activity=derive_activity(tools, turns),
    )


def rank_key(actor: Actor):
    """Order characters so the most interesting ones are visible when capped.

    Active first, then idle, then subagents, then stale/completed.
    """
    order = {STATE_ACTIVE: 0, STATE_IDLE: 1, STATE_STALE: 2, STATE_COMPLETED: 3}
    return (order.get(actor.state, 9), 0 if actor.is_subagent else 1, -actor.activity)
