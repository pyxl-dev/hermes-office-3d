# Hermes Office 3D

A browser-based, mobile-friendly, low-poly 3D office that visualizes your
**real, currently-running Hermes Agent sessions** — one animated character per
persisted session, plus subagents when the API reports them.

It is **read-only** and **private by default**: the browser only ever talks to
this app's own server, which reads the local Hermes API server-side and hands
the front-end a small, anonymised snapshot. No session titles, prompts,
transcripts, ids, paths or keys ever reach the browser.

> **This GitHub repository is source only.** Cloning it does not publish your
> office. The runtime is a local, token-guarded server on `127.0.0.1` that you
> start yourself. A public source repo is **not** a public deployment.

---

## Why this base

Two open-source candidates were inspected first:

| Project | License | Verdict |
|---|---|---|
| [VirtOffice](https://github.com/OneByJorah/VirtOffice) | MIT | **Chosen.** Zero-dependency Python server + a single-file Three.js office with animated avatars and office zones. Its Hermes "integration" polls a `/api/agents/status` endpoint that Hermes does not expose, and its data model invents `mood`/`tasksDone`/`hours`. We keep the *look* (avatars, zones) and replace the *data layer* with a real, observable-only adapter. |
| [Hermes3D](https://github.com/iamlukethedev/Hermes3D) | MIT | Rejected. Next.js 16 + React Three Fiber + Phaser + a Node WebSocket proxy + Spotify/voice/standup surfaces — much more surface area than a read-only MVP needs. No code taken. |

See [`NOTICE.md`](NOTICE.md) for attribution.

---

## What one character means (the honesty contract)

Every character corresponds to a **real row** returned by the Hermes API's
`GET /api/sessions`. Nothing is fabricated:

| Shown | Source field | Notes |
|---|---|---|
| one character per session | `id` | id is hashed to a run-scoped pseudonym (`s-…`) |
| `active` / `idle` / `stale` | `last_active`, `ended_at` | recency thresholds below |
| `completed` | `ended_at` present | |
| subagent ring + parent link | `parent_session_id`, `is_internal_child` | child sessions, requested with `include_children=true` |
| tool calls / turns | `tool_call_count`, `message_count` | plain counts |
| activity % | counts (log-saturated) | derived, not random |
| origin | `source` | bucketed to `local` / `remote` / `agent` |

Zone placement (`Workstation`, `Collab corner`, `Lounge`, `Quiet booth`,
`Archive`) is a **presentation choice** tied to state — it is documented as
such and never presented as a fact about what a session is doing.

### State thresholds

| State | Condition |
|---|---|
| `active` | not ended and `now - last_active ≤ ACTIVE_SECONDS` (default 120s) |
| `idle` | not ended and `now - last_active ≤ IDLE_SECONDS` (default 900s) |
| `stale` | not ended and older than `IDLE_SECONDS` |
| `completed` | `ended_at` is set |

### Never exposed to the browser

`title`, `preview`, `system_prompt`, message content, `user_id`, model name,
raw `source`, file paths, costs, the Hermes API key, and any raw session id.

---

## Quick start (macOS / Linux)

Requires **Python 3.9+**. The runtime is standard-library only — nothing to
`pip install`.

### 1. Demo mode (no secrets, no Hermes)

```bash
git clone https://github.com/pyxl-dev/hermes-office-3d.git
cd hermes-office-3d
python3 -m hermes_office --demo
```

Open the printed URL and sign in with the token from
`~/.hermes-office-token` (a random one is generated on first run and written
there with mode `0600`). You will see eight **synthetic** characters (their ids
start with `demo-`) covering every state.

### 2. Live mode (your real sessions)

```bash
cp .env.example .env
# set a strong HERMES_OFFICE_TOKEN and your gateway key:
#   HERMES_OFFICE_TOKEN=<pick-a-long-random-string>
#   HERMES_API_KEY=<your Hermes API_SERVER_KEY>
# (the key lives in ~/.hermes/.env as API_SERVER_KEY; copy it, don't commit it)
python3 -m hermes_office
```

Then open `http://127.0.0.1:8765`, sign in with your token, and your live
office appears. If the API is configured but unreachable, the UI says so and
shows nothing rather than inventing characters.

---

## Configuration

All configuration is environment variables; see [`.env.example`](.env.example).
`python3 -m hermes_office --help` also lists `--host`, `--port`, `--demo`,
`--verbose`. There are no hard-coded personal values anywhere in the repo.

---

## Security & privacy

Read [`SECURITY.md`](SECURITY.md) and [`docs/PRIVACY.md`](docs/PRIVACY.md).
The short version:

- binds to `127.0.0.1` by default — never a public interface;
- **every** route (UI, `/api/office`, `/events`) requires a bearer token or a
  signed-in `HttpOnly; SameSite=Strict` cookie — there is no anonymous
  dashboard;
- the browser never reaches the Hermes API; the key stays server-side;
- strict CSP, `X-Frame-Options: DENY`, `nosniff`, no wildcard CORS;
- the payload is built from a strict allow-list, ids are pseudonymised with a
  per-run salt.

### Secure phone access

Remote access is **off by default**. To view the office from your phone over a
private tailnet, see [`docs/MOBILE_ACCESS.md`](docs/MOBILE_ACCESS.md) — the
recommended path is `tailscale serve` (private tailnet URL) plus the office's
own token. Never expose `127.0.0.1:8642`; never expose the office without its
token.

---

## Tests

```bash
python3 -m pytest tests -q
```

Covers state adaptation, redaction/pseudonymisation, the payload allow-list
(including a leak test with a titled session), the actor cap, and HTTP
boundaries (auth on every route, cookie login, security headers, no wildcard
CORS, path-traversal rejection).

There is also an automated browser smoke script:

```bash
python3 scripts/smoke.py
```

---

## Project layout

```
hermes_office/       stdlib server, adapter, redaction, state model
web/                 the 3D front-end (office.html, app.js, vendor/three.min.js)
tests/               pytest suite
docs/                privacy + mobile-access guides
```

---

## Limitations (honest)

- **Subagents** appear only if your Hermes build persists child session rows
  (`parent_session_id` / `is_internal_child`). If it does not, no subagent
  characters show — we do not fake them.
- **Per-run tool-by-tool progress** is not exposed by the session list API, so
  activity is derived from recorded counts, not live tool events.
- The office renders the most recent/ most interesting `MAX_ACTORS` sessions
  (default 48); it is a monitor, not a full session browser.
- `GET /v1/runs` is not listable, so active run *detail* is unavailable; the
  aggregate run count comes from `GET /health/detailed`.

## License

MIT — see [`LICENSE`](LICENSE). Third-party attribution in [`NOTICE.md`](NOTICE.md).
