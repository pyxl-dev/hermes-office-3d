# Security

## Model

Hermes Office 3D is a **read-only viewer**. It cannot send messages, run tools,
approve actions, stop runs or change any Hermes configuration. Its only
outbound call is a `GET` to the local Hermes API server.

```
 browser  ──(same-origin, token-guarded)──►  hermes-office server  ──(server-side, key)──►  127.0.0.1:8642
```

The browser never contacts the Hermes API. The API key lives only in the
server process environment.

## Defaults that keep you safe

- **Loopback bind.** `HERMES_OFFICE_HOST` defaults to `127.0.0.1`.
- **Everything is authenticated.** Static files, `/api/office`, `/api/config`
  and `/events` all require a matching bearer token or the sign-in cookie.
  `GET /healthz` returns `{"status":"ok"}` and nothing else.
- **Token is required, never invented as "open".** If `HERMES_OFFICE_TOKEN` is
  unset, a random one is generated and written to `~/.hermes-office-token`
  (mode `0600`) — it is never printed to the console. Comparisons use
  constant-time `hmac.compare_digest`.
- **Cookie is `HttpOnly; SameSite=Strict`** (12h), so it is not readable by
  JavaScript and not sent cross-site.
- **No CORS.** Responses carry no `Access-Control-Allow-Origin`; the app is
  same-origin only.
- **Hardened responses.** `Content-Security-Policy` (default-src 'none',
  script-src 'self'), `X-Frame-Options: DENY`, `X-Content-Type-Options:
  nosniff`, `Referrer-Policy: no-referrer`, restrictive `Permissions-Policy`.
- **Path-traversal safe** static file serving (resolved under `web/` only).

## Data minimisation

The `/api/office` payload is built from a strict allow-list
(`hermes_office/redact.py`). Session ids are pseudonymised with a **per-process
random salt**, so pseudonyms cannot be correlated across restarts. Titles,
previews, prompts, transcripts, user ids, model names, raw channel names,
paths and costs are never included. See [`docs/PRIVACY.md`](PRIVACY.md).

## Reporting

This is a personal-scale OSS project. Please open a GitHub issue for
non-sensitive reports, and avoid pasting any real session data, tokens or logs
into an issue.

## If you expose it beyond localhost

Do not. Put an authenticated, private path in front of it (for example
`tailscale serve` on a private tailnet) as described in
[`docs/MOBILE_ACCESS.md`](MOBILE_ACCESS.md), keep the office token, and keep
the Hermes API (`127.0.0.1:8642`) strictly private.
