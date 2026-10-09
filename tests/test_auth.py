from conftest import TOKEN, http, json_body


def test_healthz_is_open_but_empty(server):
    status, _, body = http(server, "/healthz")
    assert status == 200
    assert json_body(body)["status"] == "ok"


def test_api_requires_auth(server):
    status, _, _ = http(server, "/api/office")
    assert status == 401


def test_api_rejects_wrong_token(server):
    status, _, _ = http(server, "/api/office", token="wrong")
    assert status == 401


def test_api_accepts_bearer_token(server):
    status, _, body = http(server, "/api/office", token=TOKEN)
    assert status == 200
    payload = json_body(body)
    assert payload["mode"] == "demo"
    assert "actors" in payload


def test_api_accepts_header_token(server):
    status, _, _ = http(server, "/api/office", headers={"X-Office-Token": TOKEN})
    assert status == 200


def test_static_requires_auth(server):
    status, _, _ = http(server, "/office.html")
    assert status == 401


def test_static_served_with_auth(server):
    status, headers, body = http(server, "/office.html", token=TOKEN)
    assert status == 200
    assert "text/html" in headers["Content-Type"]
    assert "Hermes Office 3D" in body


def test_vendored_three_served(server):
    status, headers, _ = http(server, "/vendor/three.min.js", token=TOKEN)
    assert status == 200
    assert "javascript" in headers["Content-Type"]


def test_events_requires_auth(server):
    status, _, _ = http(server, "/events")
    assert status == 401


def test_security_headers_present(server):
    _, headers, _ = http(server, "/api/office", token=TOKEN)
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "script-src 'self'" in headers["Content-Security-Policy"]


def test_no_wildcard_cors(server):
    _, headers, _ = http(server, "/api/office", token=TOKEN)
    assert "Access-Control-Allow-Origin" not in headers


def test_path_traversal_is_blocked(server):
    status, _, _ = http(server, "/../../etc/passwd", token=TOKEN)
    assert status == 404


def test_login_flow_sets_cookie(server):
    status, headers, _ = http(
        server, "/login", method="POST", data="token=" + TOKEN
    )
    assert status == 303
    set_cookie = headers.get("Set-Cookie", "")
    assert "office_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Strict" in set_cookie
    # the cookie then authenticates a static request
    cookie = set_cookie.split(";")[0]
    status, _, body = http(server, "/api/office", cookie=cookie)
    assert status == 200


def test_login_rejects_bad_token(server):
    status, headers, _ = http(server, "/login", method="POST", data="token=nope")
    assert status == 303
    assert "/login?error=1" in headers["Location"]


def test_config_endpoint_requires_auth_and_is_sanitized(server):
    status, _, _ = http(server, "/api/config")
    assert status == 401
    status, _, body = http(server, "/api/config", token=TOKEN)
    assert status == 200
    cfg = json_body(body)
    assert "hermes_api_key" not in cfg
    assert "hermes_api_base" not in cfg
    assert "token" not in cfg


def test_token_in_query_string_is_never_accepted(server):
    # EventSource cannot set headers, so the cookie is the only browser path;
    # the token must never be accepted from (or placed in) the URL.
    assert http(server, f"/api/office?token={TOKEN}")[0] == 401
    assert http(server, f"/events?token={TOKEN}")[0] == 401
    assert http(server, f"/office.html?token={TOKEN}")[0] == 401


def test_sse_accepts_cookie_auth(server):
    # sign in, then confirm the cookie authorises the SSE route
    _, headers, _ = http(server, "/login", method="POST", data="token=" + TOKEN)
    cookie = headers["Set-Cookie"].split(";")[0]
    # read only the response line + first event through a raw socket
    import socket
    host = server.split("//")[1].split(":")
    sock = socket.create_connection((host[0], int(host[1])), timeout=5)
    sock.sendall((
        "GET /events HTTP/1.1\r\nHost: x\r\nCookie: %s\r\n"
        "Accept: text/event-stream\r\n\r\n" % cookie
    ).encode())
    sock.settimeout(5)
    head = sock.recv(200).decode("utf-8", "replace")
    sock.close()
    assert "200" in head.split("\r\n")[0]
    assert "text/event-stream" in head
