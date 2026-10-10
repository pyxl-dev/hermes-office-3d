"""Bounded consumer of real Hermes run tool events.

Wire facts (verified against the local gateway source):

* ``GET /v1/runs/{run_id}/events`` is an SSE stream; each frame is
  ``id: <seq>\\n`` + ``data: <json>\\n\\n``.
* The JSON payload is ``{"event", "run_id", "timestamp", "seq", **fields}``.
* ``tool.started`` carries ``{"tool", "preview"}`` and ``tool.completed`` carries
  ``{"tool", "duration", "error", "preview"}``. **``tool`` and ``preview`` are
  never forwarded**: ``preview`` holds tool arguments / a result summary, and the
  tool name is itself more than the client needs. Only a coarse category and a
  non-reversible synthetic key leave this module.

The tracker below is deliberately free of I/O so the whole contract is testable
with synthetic frames.
"""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.parse
import urllib.request
from typing import Any, Iterable

# Coarse categories only. Anything unrecognised is "other" so a new or
# unexpected tool name can never reach the client as itself.
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

ACTIVE_STATUSES = frozenset({"running", "started", "queued", "waiting_for_approval"})
TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed", "stopped", "error", "interrupted"})

MAX_ACTIVE_TOOLS_PER_RUN = 8


def category_for(tool: Any) -> str:
    return CATEGORY_BY_TOOL.get(str(tool or ""), "other")


def synthetic_tool_key(run_key: str, seq: Any, tool: Any) -> str:
    """Non-reversible, stable per (run, seq, tool). Reveals nothing on its own."""
    raw = f"{run_key}\0{seq}\0{tool}".encode()
    return "t-" + hashlib.sha256(raw).hexdigest()[:12]


def parse_sse_frames(chunks: Iterable[bytes]) -> Iterable[dict]:
    """Parse SSE frames into payload dicts. Ignores comments and bad JSON."""
    buffer = ""
    for chunk in chunks:
        buffer += chunk.decode("utf-8", "replace")
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            data_lines = []
            for line in block.splitlines():
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if not data_lines:
                continue
            try:
                payload = json.loads("\n".join(data_lines))
            except ValueError:
                continue
            if isinstance(payload, dict):
                yield payload


class ToolEventTracker:
    """Tracks which runs have an unmatched, real tool start.

    Rules that keep the client honest:
    * a tool is only "active" after an observed ``tool.started``;
    * a ``tool.completed`` clears it;
    * a terminal run status clears everything for that run;
    * replayed or out-of-order frames are dropped by ``seq``.
    """

    def __init__(self, pseudonymiser, *, max_tools_per_run: int = MAX_ACTIVE_TOOLS_PER_RUN) -> None:
        self.pseudonymiser = pseudonymiser
        self.max_tools_per_run = max_tools_per_run
        self._last_seq: dict[str, int] = {}
        self._active: dict[str, dict[str, dict[str, Any]]] = {}
        self._status: dict[str, str] = {}
        self._run_sessions: dict[str, str] = {}

    # -- lifecycle ---------------------------------------------------------
    def bind_run(self, run_key: str, session_id: str | None) -> None:
        """Associate a run with its verified session (from the Runs API)."""
        if session_id:
            self._run_sessions[run_key] = str(session_id)

    def forget_run(self, run_key: str) -> None:
        self._last_seq.pop(run_key, None)
        self._active.pop(run_key, None)
        self._status.pop(run_key, None)
        self._run_sessions.pop(run_key, None)

    def last_seq(self, run_key: str) -> int:
        return self._last_seq.get(run_key, -1)

    # -- event intake ------------------------------------------------------
    def handle(self, run_key: str, payload: dict) -> None:
        seq = payload.get("seq")
        if isinstance(seq, int):
            if seq <= self._last_seq.get(run_key, -1):
                return  # replay / out-of-order
            self._last_seq[run_key] = seq

        name = str(payload.get("event") or "")
        if name == "tool.started":
            tool = payload.get("tool")
            bucket = self._active.setdefault(run_key, {})
            if len(bucket) >= self.max_tools_per_run:
                return  # bounded: never grow without limit
            key = synthetic_tool_key(run_key, seq, tool)
            bucket[key] = {"category": category_for(tool)}
        elif name == "tool.completed":
            # Clear one matching start if we have it; otherwise ignore.
            bucket = self._active.get(run_key)
            if bucket:
                for key in list(bucket):
                    bucket.pop(key)
                    break
        elif name in {"run.stopping", "run.interrupted"}:
            self._active.pop(run_key, None)

    def set_status(self, run_key: str, status: str) -> None:
        """Terminal status clears activity: no stale typing after a run ends."""
        self._status[run_key] = status
        if status in TERMINAL_STATUSES:
            self._active.pop(run_key, None)

    # -- output ------------------------------------------------------------
    def snapshot(self) -> dict[str, dict[str, Any]]:
        """``{session_pseudonym: {tool_active, tool_id, category}}``.

        Runs with no observed start emit nothing, so an idle-but-running run
        never looks like it is writing code.
        """
        out: dict[str, dict[str, Any]] = {}
        for run_key, bucket in self._active.items():
            if not bucket:
                continue
            session_id = self._run_sessions.get(run_key)
            if not session_id:
                continue
            key = next(iter(bucket))
            pseudo = self.pseudonymiser(session_id)
            out[pseudo] = {
                "tool_active": True,
                "tool_id": key,
                "category": bucket[key]["category"],
            }
        return out


class RunStreamWorker:
    """Bounded background reader for confirmed-active runs.

    At most ``max_streams`` concurrent readers plus one coordinator thread. Each
    reader owns exactly one run, resumes from the tracker's cursor on reconnect,
    backs off on error, and stops on terminal status. No HTTP handler ever
    blocks on this.
    """

    def __init__(
        self,
        tracker: "ToolEventTracker",
        api_base: str,
        api_key: str,
        *,
        max_streams: int = 4,
        connect_timeout: float = 4.0,
        backoff_s: float = 2.0,
    ) -> None:
        self.tracker = tracker
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.max_streams = max_streams
        self.connect_timeout = connect_timeout
        self.backoff_s = backoff_s
        self._stop = threading.Event()
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        threading.Thread(target=self._coordinate, daemon=True, name="runstream-coord").start()

    def stop(self) -> None:
        self._stop.set()

    def active_stream_count(self) -> int:
        with self._lock:
            return len(self._threads)

    # -- internals ---------------------------------------------------------
    def _coordinate(self) -> None:
        while not self._stop.is_set():
            try:
                self._reconcile()
            except Exception:
                pass
            self._stop.wait(self.backoff_s)

    def _reconcile(self) -> None:
        """Start readers for known runs, drop readers for runs that ended."""
        with self._lock:
            for run_key in list(self._threads):
                thread = self._threads[run_key]
                if not thread.is_alive():
                    self._threads.pop(run_key, None)

    def track_run(self, run_key: str, session_id: str | None) -> None:
        """Called by the discovery path once a run is API-confirmed active."""
        self.tracker.bind_run(run_key, session_id)
        with self._lock:
            if run_key in self._threads or len(self._threads) >= self.max_streams:
                return  # dedupe: never two readers for one run, never unbounded
            thread = threading.Thread(
                target=self._read_run, args=(run_key,), daemon=True, name="runstream"
            )
            self._threads[run_key] = thread
        thread.start()

    def _read_run(self, run_key: str) -> None:
        url = f"{self.api_base}/v1/runs/{urllib.parse.quote(run_key)}/events"
        while not self._stop.is_set():
            seq = self.tracker.last_seq(run_key)
            request = urllib.request.Request(
                f"{url}?last_seq={seq}",
                headers={"Authorization": f"Bearer {self.api_key}", "Accept": "text/event-stream"},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.connect_timeout) as resp:
                    if resp.status != 200:
                        self.tracker.forget_run(run_key)
                        return
                    for payload in parse_sse_frames(iter(lambda: resp.read(4096), b"")):
                        self.tracker.handle(run_key, payload)
            except Exception:
                # A dropped connection is retried, not fatal; a run that is gone
                # simply stops being tracked.
                pass
            if self._stop.wait(self.backoff_s):
                return
            status = self.tracker._status.get(run_key, "")
            if status in TERMINAL_STATUSES:
                self.tracker.forget_run(run_key)
                return
