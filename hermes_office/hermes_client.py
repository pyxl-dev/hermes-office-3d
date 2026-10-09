"""Server-side client for the local Hermes API server.

This module is the *only* place that sees the Hermes API key and raw session
rows. It deliberately returns nothing but the allow-listed fields and never
logs response bodies (they contain session titles/previews).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from .config import Settings
from .redact import ROW_READ_ALLOWLIST

logger = logging.getLogger("hermes_office.client")

TIMEOUT_S = 8


class HermesClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _get(self, path: str) -> dict | None:
        url = self.settings.hermes_api_base + path
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": "Bearer " + self.settings.hermes_api_key,
                "Accept": "application/json",
                "User-Agent": "hermes-office-3d",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Never echo the body: it can contain upstream diagnostics.
            logger.warning("Hermes API %s -> HTTP %s", path, exc.code)
            return None
        except Exception as exc:  # noqa: BLE001 - network/JSON failures are expected
            logger.warning("Hermes API %s unreachable: %s", path, type(exc).__name__)
            return None

    @staticmethod
    def _allowlist(row: dict) -> dict:
        return {k: row[k] for k in row if k in ROW_READ_ALLOWLIST}

    def fetch_sessions(self, limit: int = 200) -> list[dict] | None:
        """Return up to ``limit`` allow-listed session rows, or None on failure.

        ``include_children=true`` is required so subagent/child sessions appear.
        """
        payload = self._get(
            f"/api/sessions?limit={int(limit)}&include_children=true"
        )
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        if not isinstance(data, list):
            return None
        return [self._allowlist(r) for r in data if isinstance(r, dict)]

    def fetch_health(self) -> dict | None:
        payload = self._get("/health/detailed")
        return payload if isinstance(payload, dict) else None
