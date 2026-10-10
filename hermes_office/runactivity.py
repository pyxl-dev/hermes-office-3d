"""Optional, read-only observation of locally recorded Hermes run activity.

Scope and honesty
-----------------
This reads a *local* activity log that another process writes when it drives
Hermes runs (the A2A bridge). It is deliberately narrow:

* Only a bounded tail is read, and only an allowlist of fields is used. Tool
  names, run ids, session ids, previews, goals, arguments, results and paths are
  never returned to callers, never logged, and never put on the wire.
* A session is reported as ``working`` only when a recorded call *ended* within a
  short window. The log is append-on-completion, so an open call cannot be
  observed; anything older than the window is reported as ``recent``.
* Sessions that this log never mentions stay neutral. The feature is therefore
  honest about being partial: it covers runs driven through that one bridge, not
  every Hermes conversation.

The observer is disabled unless a path is configured.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Iterable

# Coarse categories only. Unknown tools map to "other" by design, so a new or
# unexpected tool name can never leak through as itself.
CATEGORY_BY_TOOL = {
    "read_file": "code",
    "write_file": "code",
    "patch": "code",
    "search_files": "search",
    "web_search": "search",
    "web_extract": "search",
    "terminal": "terminal",
    "execute_code": "terminal",
    "skill_view": "review",
    "skill_manage": "review",
}

# Run statuses that mean the run is genuinely executing right now. Anything else
# (completed / cancelled / failed) is history, not activity.
ACTIVE_RUN_STATUSES = frozenset({"running", "started", "queued", "waiting_for_approval"})
TERMINAL_RUN_STATUSES = frozenset({"completed", "cancelled", "failed", "stopped", "error"})

ALLOWED_FIELDS = frozenset(
    {"tool", "status", "ok", "startedAt", "endedAt", "outputSessionId", "outputRunId"}
)

WORKING_WINDOW_S = 20.0
RECENT_WINDOW_S = 300.0


def _age_bucket(age_s: float) -> str:
    """Coarse age buckets: exact timings are not the client's business."""
    if age_s < WORKING_WINDOW_S:
        return "now"
    if age_s < 60:
        return "minute"
    if age_s < RECENT_WINDOW_S:
        return "minutes"
    return "older"


def _parse_ts(value: Any) -> float | None:
    """Parse an ISO timestamp, honouring offsets and the Z suffix.

    ``strptime`` on the first 19 chars silently discarded the offset, which is
    hours wrong for a local-time log.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


class RunActivityObserver:
    """Reads a bounded tail of a local run-activity log. Never writes to it."""

    def __init__(
        self,
        path: str,
        pseudonymiser,
        *,
        tail_lines: int = 300,
        max_records: int = 200,
        resolve_run=None,
        resolve_ttl_s: float = 10.0,
        max_resolutions: int = 16,
    ) -> None:
        self.path = path
        self.pseudonymiser = pseudonymiser
        self.tail_lines = tail_lines
        self.max_records = max_records
        # Optional authoritative lookup: run_id -> {"session_id", "status"}.
        # The activity log is only a *discovery* source; a run counts as working
        # only when the Runs API confirms it. Injected so tests stay offline.
        self.resolve_run = resolve_run
        self.resolve_ttl_s = resolve_ttl_s
        self.max_resolutions = max_resolutions
        self._cache: dict[str, tuple[float, dict | None]] = {}

    def enabled(self) -> bool:
        return bool(self.path) and os.path.isfile(self.path)

    def _tail(self) -> list[bytes]:
        # Bounded read: never load the whole file, which grows without limit.
        try:
            with open(self.path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                block = min(size, 256 * 1024)
                handle.seek(size - block)
                data = handle.read()
        except OSError:
            return []
        return data.splitlines()[-self.tail_lines :]

    def _resolve(self, run_id: str, now: float) -> dict | None:
        """Cached, bounded run lookup. Never raises; never returns raw ids to the wire."""
        if self.resolve_run is None:
            return None
        hit = self._cache.get(run_id)
        if hit is not None and (now - hit[0]) < self.resolve_ttl_s:
            return hit[1]
        try:
            value = self.resolve_run(run_id)
        except Exception:
            value = None
        if not isinstance(value, dict):
            value = None
        if len(self._cache) >= self.max_resolutions:
            oldest = min(self._cache.items(), key=lambda kv: kv[1][0])[0]
            self._cache.pop(oldest, None)
        self._cache[run_id] = (now, value)
        return value

    def observe(self, now: float | None = None) -> dict[str, dict[str, Any]]:
        """Return ``{pseudonym: {state, category, age}}``. Ids never escape."""
        if not self.enabled():
            return {}
        now = now if now is not None else time.time()
        latest: dict[str, dict[str, Any]] = {}

        for raw in self._tail():
            try:
                record = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if not isinstance(record, dict):
                continue

            # Allowlist: anything else in the record is ignored outright.
            session_id = record.get("outputSessionId")
            if not session_id:
                continue
            observed = _parse_ts(record.get("endedAt")) or _parse_ts(record.get("startedAt"))
            if observed is None:
                continue
            age = now - observed
            if age < 0 or age > RECENT_WINDOW_S:
                continue

            status = str(record.get("status") or "").lower()
            has_run = bool(record.get("outputRunId"))
            tool = str(record.get("tool") or "")

            # Strict: a bridge call is never proof of work. A session is
            # "working" only when the Runs API confirms an active status *and*
            # returns the session id; anything less stays neutral.
            state = "recent"
            if has_run and status in ACTIVE_RUN_STATUSES:
                confirmed = self._resolve(str(record.get("outputRunId")), now)
                if (
                    confirmed
                    and str(confirmed.get("status") or "").lower() in ACTIVE_RUN_STATUSES
                    and confirmed.get("session_id")
                ):
                    state = "working"
                    session_id = confirmed["session_id"]

            category = CATEGORY_BY_TOOL.get(tool, "other")
            previous = latest.get(pseudo := self.pseudonymiser(str(session_id)))
            if previous is None or age < previous["_age"]:
                latest[pseudo] = {
                    "_age": age,
                    "state": state,
                    "category": category,
                    "age": _age_bucket(age),
                }

        out: dict[str, dict[str, Any]] = {}
        for pseudo, entry in list(latest.items())[: self.max_records]:
            out[pseudo] = {
                "state": entry["state"],
                "category": entry["category"],
                "age": entry["age"],
            }
        return out


def observe_or_empty(observer: "Any", now: float | None = None) -> dict:
    """Never let an observability problem break the office payload."""
    if observer is None:
        return {}
    try:
        return observer.observe(now)
    except Exception:
        return {}
