# Changelog

## 0.1.0 — initial MVP

- Read-only 3D office: one animated character per real Hermes session, plus
  subagent characters when the API reports child sessions.
- Server-side sanitized adapter for the local Hermes API (`/api/sessions`,
  `/health/detailed`) with strict allow-list and per-run pseudonymisation.
- Stdlib-only HTTP server: same-origin static UI, `/api/office`, `/events` SSE,
  token auth on every route, security headers, no CORS.
- Low-poly front-end with camera orbit (mouse + touch), responsive mobile
  layout, sanitized details panel, and a clear demo/live badge.
- Demo mode with synthetic fixtures for offline use and testing.
- Dependency-free `.env` loader (`load_env_file`) so `cp .env.example .env` works
  as documented; real environment variables always win and values are never
  logged.
- Test suite (state, redaction, adapter boundary, HTTP auth/security, `.env`
  parsing, and relative-link checks for the docs).
