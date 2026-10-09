#!/usr/bin/env python3
"""End-to-end smoke test: boot the demo server and exercise it over HTTP.

No Hermes API, no secrets, no browser. Exits non-zero on the first failure.
Run:  python3 scripts/smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hermes_office.config import Settings  # noqa: E402
from hermes_office.server import build_server  # noqa: E402

TOKEN = "smoke-token"
FAILURES = []


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def get(base, path, token=None):
    headers = {"Authorization": "Bearer " + token} if token else {}
    req = urllib.request.Request(base + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8", "replace")


def main() -> int:
    settings = Settings(host="127.0.0.1", port=0, office_token=TOKEN, hermes_api_key="", poll_seconds=1)
    httpd = build_server(settings)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    print(f"server at {base}\n")

    status, _, body = get(base, "/healthz")
    check("/healthz open, no data", status == 200 and json.loads(body) == {"status": "ok", "service": "hermes-office-3d"})

    status, _, _ = get(base, "/api/office")
    check("/api/office requires auth", status == 401)

    status, _, _ = get(base, "/office.html")
    check("static requires auth", status == 401)

    status, headers, body = get(base, "/api/office", token=TOKEN)
    ok = status == 200
    payload = json.loads(body) if ok else {}
    check("/api/office with token", ok and payload.get("mode") == "demo")
    check("payload has actors", len(payload.get("actors", [])) > 0)
    check("no wildcard CORS", "Access-Control-Allow-Origin" not in headers)
    check("CSP present", "content-security-policy" in {k.lower() for k in headers})

    blob = body.lower()
    for bad in ("system_prompt", "user_id", "/users/", "api_server_key"):
        check(f"payload excludes {bad!r}", bad not in blob)

    from hermes_office.redact import FORBIDDEN_KEYS

    def all_keys(obj, acc=None):
        acc = acc if acc is not None else set()
        if isinstance(obj, dict):
            acc |= set(obj)
            for v in obj.values():
                all_keys(v, acc)
        elif isinstance(obj, list):
            for v in obj:
                all_keys(v, acc)
        return acc

    leaked = FORBIDDEN_KEYS & all_keys(payload)
    check("payload has no forbidden keys", not leaked, f"leaked={sorted(leaked)}")

    status, _, body = get(base, "/office.html", token=TOKEN)
    check("UI served", status == 200 and "Hermes Office 3D" in body)

    status, _, body = get(base, "/vendor/three.min.js", token=TOKEN)
    check("vendored three.js served", status == 200 and "Three.js" in body)

    status, _, _ = get(base, "/../../etc/passwd", token=TOKEN)
    check("path traversal blocked", status == 404)

    httpd.shutdown()
    httpd.server_close()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {', '.join(FAILURES)}")
        return 1
    print("all smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
