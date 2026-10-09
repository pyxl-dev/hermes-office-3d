import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hermes_office.config import Settings  # noqa: E402
from hermes_office.server import build_server  # noqa: E402

TOKEN = "test-token-abc123"


@pytest.fixture
def settings():
    return Settings(
        host="127.0.0.1",
        port=0,
        office_token=TOKEN,
        hermes_api_key="",  # demo mode: no network, no secrets
        poll_seconds=1,
    )


@pytest.fixture
def server(settings):
    httpd = build_server(settings)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base
    finally:
        httpd.shutdown()
        httpd.server_close()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http(base, path, *, method="GET", token=None, cookie=None, headers=None, data=None):
    """Return (status, headers, body). Never follows redirects."""
    req_headers = dict(headers or {})
    if token:
        req_headers["Authorization"] = "Bearer " + token
    if cookie:
        req_headers["Cookie"] = cookie
    body = None
    if data is not None:
        body = data.encode("utf-8")
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(base + path, data=body, method=method, headers=req_headers)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read().decode("utf-8", "replace")


def json_body(text):
    return json.loads(text)
