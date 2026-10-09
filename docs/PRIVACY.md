# Privacy

What the browser can and cannot learn about your Hermes sessions.

## Never leaves the server

- Session **titles** and **previews**
- **System prompts**, message content, transcripts, tool arguments/results
- **User ids**, emails, chat/channel identities
- **Raw session ids** and parent ids
- **Model names**, raw `source` values
- File paths, working directories, costs / billing
- The Hermes **API key** and the office access token (except the token you type
  at sign-in, which becomes an `HttpOnly` cookie)

## Reaches the browser (the whole payload)

```jsonc
{
  "mode": "live",                 // or "demo"
  "degraded": false,              // live configured but unreachable
  "generated_at": 1728...,        // unix seconds
  "summary": {"sessions": 0, "active": 0, "idle": 0, "stale": 0,
               "completed": 0, "subagents": 0},
  "gateway": {"available": true, "active_runs": 0, "stored_runs": 0,
               "active_agents": 0, "busy": false, "version": "0.21.5"},
  "capabilities": {"subagents": true, "runs_detail": false, "transcripts": false},
  "notes": ["..."],
  "actors": [
    {
      "id": "s-1a2b3c4d5e",   // per-run pseudonym
      "state": "active",       // active|idle|stale|completed
      "zone": "desk",          // presentation zone
      "origin": "local",       // local|remote|agent|unknown
      "is_subagent": false,
      "parent": "",            // pseudonym of parent, if any
      "age_sec": 12,           // since last activity
      "duration_sec": 640,
      "tools": 27, "messages": 41, "turns": 20,
      "ended": false,
      "activity": 0.61         // 0..1, from the counts above
    }
  ]
}
```

## Pseudonymisation

`id` and `parent` are `s-` + `HMAC-SHA256(random_per_process_salt, raw_id)`
truncated to 10 hex chars. Same raw id → same pseudonym **within one server
run**; different salt each restart, so pseudonyms are not comparable across
runs and cannot be reversed.

## Demo mode

`--demo` (or an empty `HERMES_API_KEY`) serves synthetic fixtures from
`hermes_office/fixtures.py` whose ids all start with `demo-`. They are never
mixed with live rows.

## Logging

The server logs counts and transport-level warnings only. Response bodies are
never logged, and a `redact_text()` helper scrubs paths/token-shaped strings
from any free text used in diagnostics.
