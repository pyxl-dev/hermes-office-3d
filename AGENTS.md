# Instructions for AI agents

You are an AI coding agent (Claude Code, Codex, Cursor...) and your user asked you to install or run **Hermes Office 3D**. This file tells you how. Keep the safety rules at the end: they matter more than the rest.

## What it does

A read-only viewer for Hermes Agent sessions: a small standard-library Python server (no dependencies) reads the local Hermes API server-side and serves an animated office in the browser, one character per recently active session, subagents included. The browser only ever talks to this server and receives an anonymised snapshot: no titles, prompts, transcripts, ids, paths or keys. The root URL opens a 2D pixel-art office; the older 3D view is at `/office.html`. It cannot send messages, run tools or stop runs.

Without `HERMES_API_KEY`, or with `--demo`, it serves synthetic fixtures (demo mode). Needs Python 3.9+ and git.

## Install

Run, then read the output: every line starts with `✓`, `!` (optional piece missing) or `✗` (blocking).

```sh
curl -fsSL https://raw.githubusercontent.com/pyxl-dev/hermes-office-3d/main/install.sh | sh
```

- `✗ python3 is missing` or `Python 3.9+ is required`: tell the user. Do not install system tools without asking.
- `! ... is not on your PATH`: give the user the `export PATH=...` line it prints.
- It installs the code in `~/.local/share/hermes-office-3d` and a `hermes-office-3d` command in `~/.local/bin`. Re-run it to update; `--uninstall` removes both.
- Check: `hermes-office-3d --help` prints the usage.

From a clone, `./install.sh` installs that clone, or skip the installer and use `python3 -m hermes_office`.

## Use

1. Demo mode, no secrets: start `hermes-office-3d --demo` **in the background** (it blocks).
2. Read its output: the URL (default `http://127.0.0.1:8765`) and, if no `HERMES_OFFICE_TOKEN` is set, a note that a random token was written to `~/.hermes-office-token`. The token is never printed.
3. The user signs in at the URL with that token. Do not read the token file out loud or paste it in chat; tell the user where it is.
4. Live mode: the user must put `HERMES_API_KEY` (the Hermes `API_SERVER_KEY`) and a `HERMES_OFFICE_TOKEN` in `.env` inside the install folder (copy `.env.example`). Do not read or copy the Hermes key yourself unless the user asks you to; never commit `.env`.
5. Phone access, only if the user wants it: `tailscale serve --bg --https=443 http://127.0.0.1:8765`. See `docs/MOBILE_ACCESS.md`.
6. Stop the background process when the task is over.

Development: `python3 -m pytest tests -q`, `python3 scripts/smoke.py`, `make check`.

## Safety rules

- Never expose or proxy the Hermes API (`127.0.0.1:8642`): it holds the user's key.
- Keep the office bound to `127.0.0.1`. Do not pass `--host 0.0.0.0` or set `HERMES_OFFICE_ALLOW_REMOTE=1` without an authenticated private path (for example `tailscale serve`). Never use `tailscale funnel`.
- Never print, log, commit or paste the office token or `HERMES_API_KEY`. Never commit `.env`.
- Never add a field to the `/api/office` payload without updating the allow-list and its leak tests (`hermes_office/redact.py`, `tests/`): titles, previews, prompts, ids, paths and costs must never reach the browser.
- Do not turn the viewer into a controller: it is read-only on purpose.
