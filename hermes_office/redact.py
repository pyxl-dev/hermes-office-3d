"""Privacy boundary: pseudonymisation and a strict output allow-list.

Everything that leaves this module is safe to hand to a browser. Session ids,
titles, previews, end reasons, file paths, model names and raw source names are
either hashed into a run-scoped pseudonym or dropped entirely — they never
appear in an :class:`~hermes_office.adapter` payload.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# Fields we are willing to *read* from an upstream session row. Anything not in
# this set is ignored, so a future Hermes field can never leak by accident.
ROW_READ_ALLOWLIST = frozenset(
    {
        "id",
        "source",
        "started_at",
        "last_active",
        "ended_at",
        "end_reason",
        "message_count",
        "tool_call_count",
        "api_call_count",
        "parent_session_id",
        "is_internal_child",
        "pinned",
        "archived",
        "hidden",
    }
)

# Keys that must never appear in an emitted actor, whatever the input.
FORBIDDEN_KEYS = frozenset(
    {
        "title",
        "preview",
        "system_prompt",
        "prompt",
        "content",
        "messages",
        "path",
        "cwd",
        "user_id",
        "email",
        "token",
        "key",
        "secret",
        "cost",
    }
)


class Pseudonymiser:
    """Maps raw identifiers to stable, non-reversible, run-scoped pseudonyms.

    A fresh random salt is minted per process, so pseudonyms cannot be
    correlated across restarts (and mean nothing outside this process).
    """

    def __init__(self, salt: bytes | None = None) -> None:
        self._salt = salt or secrets.token_bytes(16)

    def __call__(self, raw: object, prefix: str = "s") -> str:
        if raw is None or str(raw) == "":
            return ""
        digest = hmac.new(
            self._salt, str(raw).encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"{prefix}-{digest[:10]}"

    @staticmethod
    def short(token: str) -> str:
        """A short display-safe digest of a pseudonym (for parent links)."""
        return "p-" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


def scrub_actor(actor: dict) -> dict:
    """Defence in depth: drop any forbidden key from an actor before emission."""
    return {k: v for k, v in actor.items() if k not in FORBIDDEN_KEYS}


def redact_text(text: object) -> str:
    """Best-effort scrub of a free-text string for diagnostics.

    Used only for logging paths; the office payload never carries free text.
    Removes absolute paths and looks-like-secret tokens.
    """
    if text is None:
        return ""
    s = str(text)
    out = []
    for chunk in s.replace("\n", " ").split(" "):
        if "/" in chunk and chunk.count("/") >= 1 and len(chunk) > 3:
            out.append("[path]")
        elif len(chunk) >= 24 and all(
            c.isalnum() or c in "-_" for c in chunk
        ):
            out.append("[token]")
        else:
            out.append(chunk)
    return " ".join(out)[:200]
