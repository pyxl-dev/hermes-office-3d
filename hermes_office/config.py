"""Runtime configuration, read exclusively from environment variables.

No personal values are hard-coded here. Every default is safe for a local,
single-user machine; anything that widens exposure must be set explicitly.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass
class Settings:
    """All tunables for the office server."""

    # Where the 3D front-end listens. Loopback by default: never bind a public
    # interface unless you have put authenticated access in front of it.
    host: str = "127.0.0.1"
    port: int = 8765

    # Upstream Hermes API server (the local gateway). The browser NEVER talks to
    # this directly; only this server does, server-side.
    hermes_api_base: str = "http://127.0.0.1:8642"
    hermes_api_key: str = ""

    # Token that guards every route (static, API and SSE). Generated when unset
    # so the app is never unauthenticated by accident.
    office_token: str = ""

    # How often the server refreshes the upstream snapshot / pushes SSE.
    poll_seconds: int = 4

    # Recency thresholds (seconds) used to derive visible state from observable
    # session data only.
    active_window_s: int = 120
    idle_window_s: int = 900

    # Upper bound on characters rendered in the office.
    max_actors: int = 48

    # Binding to anything but loopback is refused unless this is explicitly set.
    allow_remote: bool = False

    # Session sources that mean "agent-to-agent" rather than a person.
    agent_sources: frozenset = field(
        default_factory=lambda: frozenset(
            {"a2a", "peer", "delegate", "subagent", "bridge"}
        )
    )

    # Session sources treated as a local operator (same machine).
    local_sources: frozenset = field(
        default_factory=lambda: frozenset(
            {"api_server", "cli", "oneshot", "desktop", "tui", "gateway", "cron"}
        )
    )

    @property
    def demo_mode(self) -> bool:
        """True when we have no way to reach a real Hermes API."""
        return not self.hermes_api_key

    def ensure_token(self) -> str:
        """Return the guard token, generating an ephemeral one when unset.

        A token containing whitespace, ``;`` or control characters would break
        the cookie it is stored in, so we reject it loudly at startup.
        """
        if not self.office_token:
            self.office_token = secrets.token_urlsafe(24)
        if not all(c.isalnum() or c in "-_." for c in self.office_token):
            raise ValueError(
                "HERMES_OFFICE_TOKEN must contain only letters, digits and -_."
            )
        return self.office_token

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=_env("HERMES_OFFICE_HOST", "127.0.0.1"),
            port=_env_int("HERMES_OFFICE_PORT", 8765),
            hermes_api_base=_env("HERMES_API_BASE", "http://127.0.0.1:8642").rstrip("/"),
            hermes_api_key=_env("HERMES_API_KEY"),
            office_token=_env("HERMES_OFFICE_TOKEN"),
            poll_seconds=max(1, _env_int("HERMES_OFFICE_POLL_SECONDS", 4)),
            active_window_s=max(1, _env_int("HERMES_OFFICE_ACTIVE_SECONDS", 120)),
            idle_window_s=max(1, _env_int("HERMES_OFFICE_IDLE_SECONDS", 900)),
            max_actors=max(1, _env_int("HERMES_OFFICE_MAX_ACTORS", 48)),
            allow_remote=_env_bool("HERMES_OFFICE_ALLOW_REMOTE", False),
        )
