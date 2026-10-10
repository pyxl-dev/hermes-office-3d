"""Zero-dependency HTTP server for Hermes Office 3D.

Responsibilities:

* serve the static 3D front-end from ``web/`` (same origin as the API),
* expose a **sanitized** ``/api/office`` snapshot,
* push the same snapshot over ``/events`` (Server-Sent Events),
* guard *every* route with a bearer token / signed-in cookie.

The browser never reaches the Hermes API server: this process reads it
server-side and hands the browser only anonymised, aggregated fields.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import queue
import secrets
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .adapter import build_payload
from .config import Settings
from .hermes_client import HermesClient
from .redact import Pseudonymiser

logger = logging.getLogger("hermes_office.server")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
COOKIE_NAME = "office_token"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", ""})
_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".map": "application/json; charset=utf-8",
}

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ),
}


class Store:
    """Holds the latest sanitized payload and fans it out to SSE clients."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        # A single random salt for this server's lifetime keeps each avatar
        # stable across 4-second refreshes, without exposing its raw session id.
        self._pseudonymiser = Pseudonymiser()
        self._payload: dict = build_payload(settings, pseudonymiser=self._pseudonymiser) if settings.demo_mode else {
            "mode": "live", "degraded": True, "generated_at": time.time(),
            "summary": {}, "gateway": {"available": False}, "capabilities": {},
            "notes": [], "actors": [],
        }
        self._subscribers: set[queue.Queue] = set()
        self._client = HermesClient(settings)

    def payload(self) -> dict:
        with self._lock:
            return self._payload

    def refresh(self) -> dict:
        payload = build_payload(
            self.settings, client=self._client,
            pseudonymiser=self._pseudonymiser,
        )
        with self._lock:
            self._payload = payload
            subs = list(self._subscribers)
        blob = json.dumps(payload)
        dead = []
        for q in subs:
            try:
                q.put_nowait(blob)
            except queue.Full:
                # A client that cannot keep up is dropped so it reconnects and
                # gets a fresh snapshot rather than sitting on stale data.
                dead.append(q)
        if dead:
            with self._lock:
                for q in dead:
                    self._subscribers.discard(q)
        return payload

    def is_subscribed(self, q: queue.Queue) -> bool:
        with self._lock:
            return q in self._subscribers

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=8)
        with self._lock:
            self._subscribers.add(q)
        q.put_nowait(json.dumps(self.payload()))
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)


def _compute_token(settings: Settings) -> str:
    return settings.ensure_token()


def _check_bind(settings: Settings) -> None:
    """Force loopback by default: binding wider is a deliberate, explicit act.

    The office has no business listening on a public interface; remote access
    should go through an authenticated path (e.g. `tailscale serve`).
    """
    if settings.host in _LOOPBACK_HOSTS or settings.allow_remote:
        return
    raise ValueError(
        f"refusing to bind {settings.host!r}: only loopback is allowed by default. "
        "Set HERMES_OFFICE_ALLOW_REMOTE=1 if you really mean to expose it."
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "hermes-office/" + __version__
    protocol_version = "HTTP/1.1"

    # populated by the factory
    settings: Settings
    token: str
    store: Store

    # -- helpers ---------------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - quiet by default
        logger.debug("%s - %s", self.address_string(), fmt % args)

    def _client_token(self) -> str:
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        header = self.headers.get("X-Office-Token")
        if header:
            return header.strip()
        raw = self.headers.get("Cookie")
        if raw:
            try:
                cookie = SimpleCookie()
                cookie.load(raw)
                if COOKIE_NAME in cookie:
                    return cookie[COOKIE_NAME].value
            except Exception:  # noqa: BLE001
                return ""
        return ""

    def _authed(self) -> bool:
        supplied = self._client_token()
        if not supplied:
            return False
        return hmac.compare_digest(supplied, self.token)

    def _finish_headers(self, extra: dict | None = None) -> None:
        for key, value in _SECURITY_HEADERS.items():
            self.send_header(key, value)
        for key, value in (extra or {}).items():
            self.send_header(key, value)

    def _json(self, data, status: int = 200, extra: dict | None = None) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._finish_headers(extra)
        self.end_headers()
        self.wfile.write(body)

    def _deny(self, status: int = 401) -> None:
        wants_html = "text/html" in (self.headers.get("Accept") or "")
        if wants_html and self.path not in ("/login",):
            self._redirect("/login")
            return
        self._json({"error": "unauthorized"}, status=status)

    def _redirect(self, location: str, extra: dict | None = None) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self._finish_headers(extra)
        self.end_headers()

    # -- routing ---------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path

        if path == "/healthz":
            self._json({"status": "ok", "service": "hermes-office-3d"})
            return
        if path == "/login":
            self._send_login(error="error=1" in (urllib.parse.urlparse(self.path).query or ""))
            return
        if path == "/logout":
            self._redirect("/login", {"Set-Cookie": f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})
            return

        if not self._authed():
            self._deny()
            return

        if path == "/api/office":
            self._json(self.store.payload())
            return
        if path == "/events":
            self._sse()
            return
        if path == "/api/config":
            self._json({
                "poll_seconds": self.settings.poll_seconds,
                "active_window_s": self.settings.active_window_s,
                "idle_window_s": self.settings.idle_window_s,
                "max_actors": self.settings.max_actors,
                "mode": self.store.payload().get("mode"),
            })
            return

        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            self._handle_login()
            return
        self._json({"error": "not_found"}, status=404)

    # -- handlers --------------------------------------------------------------
    def _send_login(self, error: bool = False) -> None:
        body = _LOGIN_HTML.replace(
            "<!--ERR-->",
            '<p class="err">Incorrect token — try again.</p>' if error else "",
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._finish_headers()
        self.end_headers()
        self.wfile.write(body)

    def _handle_login(self) -> None:
        # Cap the body read: a slow or lying client cannot make us read forever.
        length = min(int(self.headers.get("Content-Length") or 0), 8192)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        fields = urllib.parse.parse_qs(raw)
        supplied = (fields.get("token") or [""])[0]
        if supplied and hmac.compare_digest(supplied, self.token):
            # Mark the cookie Secure when TLS terminates in front of us
            # (e.g. `tailscale serve`); harmless over plain localhost HTTP.
            secure = (
                self.headers.get("X-Forwarded-Proto", "").lower() == "https"
                or self.headers.get("X-Forwarded-Ssl", "").lower() == "on"
            )
            cookie = (
                f"{COOKIE_NAME}={self.token}; Path=/; HttpOnly; "
                f"SameSite=Strict; Max-Age=43200" + ("; Secure" if secure else "")
            )
            self._redirect("/", {"Set-Cookie": cookie})
        else:
            self._redirect("/login?error=1")

    def _serve_static(self, path: str) -> None:
        rel = "office.html" if path in ("", "/") else path.lstrip("/")
        # A directory path (e.g. /pixel/) must serve its index.html, otherwise the
        # bundled app 404s when opened without the explicit filename.
        if rel in ("pixel", "pixel/"):
            rel = "pixel/index.html"
        elif rel.endswith("/"):
            rel += "index.html"
        candidate = (WEB_DIR / rel).resolve()
        try:
            candidate.relative_to(WEB_DIR.resolve())
        except ValueError:
            self._json({"error": "not_found"}, status=404)
            return
        if not candidate.is_file():
            self._json({"error": "not_found"}, status=404)
            return
        content_type = _STATIC_TYPES.get(candidate.suffix, "application/octet-stream")
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._finish_headers()
        self.end_headers()
        self.wfile.write(body)

    def _sse(self) -> None:
        q = self.store.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        # No Content-Length and no chunking: an HTTP/1.1 body with neither reads
        # until the connection closes, which is exactly SSE semantics.
        self._finish_headers()
        self.end_headers()
        try:
            while True:
                try:
                    blob = q.get(timeout=25)
                    self.wfile.write(f"data: {blob}\n\n".encode("utf-8"))
                except queue.Empty:
                    # dropped as a slow client -> close so the browser reconnects
                    if not self.store.is_subscribed(q):
                        break
                    self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.store.unsubscribe(q)


_LOGIN_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes Office — sign in</title>
<style>
 body{font-family:system-ui,sans-serif;background:#0b0b12;color:#e8e8f0;
      display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
 form{background:#14141f;padding:2rem;border-radius:14px;width:min(340px,90vw);
      box-shadow:0 10px 40px rgba(0,0,0,.5)}
 h1{font-size:1.1rem;margin:0 0 .4rem}
 p{font-size:.8rem;color:#9aa;margin:0 0 1rem}
 input{width:100%;padding:.7rem;border-radius:8px;border:1px solid #333;
       background:#0b0b12;color:#fff;box-sizing:border-box}
 button{margin-top:.9rem;width:100%;padding:.7rem;border:0;border-radius:8px;
        background:#6d5efc;color:#fff;font-weight:600;cursor:pointer}
 .err{color:#ff8080;font-size:.8rem}
</style></head>
<body><form method="post" action="/login">
 <h1>Hermes Office 3D</h1>
 <p>Private view. Enter the office access token.</p>
 <!--ERR-->
 <input type="password" name="token" autocomplete="current-password"
        placeholder="access token" autofocus>
 <button type="submit">Enter</button>
</form></body></html>"""


def build_server(settings: Settings) -> ThreadingHTTPServer:
    _check_bind(settings)
    token = _compute_token(settings)
    store = Store(settings)

    handler = type("BoundHandler", (Handler,), {"settings": settings, "token": token, "store": store})

    httpd = ThreadingHTTPServer((settings.host, settings.port), handler)
    httpd.daemon_threads = True
    httpd.allow_reuse_address = True
    # convenience handles for callers/tests
    httpd.token = token
    httpd.store = store
    return httpd


def _refresher(store: Store, settings: Settings, stop: threading.Event) -> None:
    while True:
        try:
            store.refresh()
        except Exception:  # noqa: BLE001 - keep the loop alive
            logger.exception("refresh failed")
        if stop.wait(settings.poll_seconds):
            break


def serve(settings: Settings) -> None:
    generated = not settings.office_token
    settings.ensure_token()
    httpd = build_server(settings)
    stop = threading.Event()
    threading.Thread(target=_refresher, args=(httpd.store, settings, stop), daemon=True).start()
    host, port = httpd.server_address[0], httpd.server_address[1]
    print(f"Hermes Office 3D  running at  http://{host}:{port}", flush=True)
    print(f"  mode: {'demo (synthetic fixtures)' if settings.demo_mode else 'live'}", flush=True)
    if generated:
        # Never print the secret to stdout (terminal history / screenshots).
        token_path = Path.home() / ".hermes-office-token"
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(settings.office_token)
        print(f"  a random access token was generated and written to {token_path} (0600).", flush=True)
        print("  read it there and sign in with it; or set HERMES_OFFICE_TOKEN yourself.", flush=True)
    else:
        print("  access token: the value of HERMES_OFFICE_TOKEN.", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.server_close()
