# Pixel Agents–style redesign — feasibility POC

**Status: visual feasibility prototype. It is NOT a Pixel Agents equivalent and is
not proposed for production.** This document records what was audited, what was
built, and why the honest recommendation is to vendor the real upstream renderer
rather than extend this prototype.

## 1. Upstream audit (read-only)

| Item | Value |
|---|---|
| Official repo | https://github.com/pixel-agents-hq/pixel-agents |
| Official commit at audit | `d1e007a9fdf3003c252d2973abe1999ae59aec33` (2026-10-08) |
| Latest release | `v1.4.1` (2026-08-15) |
| Official license | MIT — Copyright (c) 2026 Pablo De Lucca |
| Ships | VS Code extension **and** a standalone CLI (`npx pixel-agents`) that serves the office as a browser app (Node 20+) |
| Integration boundary | typed **`HookProvider`** interface; agent-agnostic, editor-agnostic |
| Renderer | Canvas2D, top-down tile grid (not isometric, not 3D) |
| Character sprites | 6 characters based on the **MetroCity pack by JIK-A-4** |

| Alternative | Value |
|---|---|
| Repo | https://github.com/Epsilondelta-ai/pixel-agents-web |
| Commit at audit | `9f37c06e44b9c1906ef6466a9e5cc9dfafede2b7` |
| License | MIT |
| Nature | Small standalone browser port (React 19 + Vite + Canvas2D, BFS pathfinding, character state machine). Demo-only data source. ~386 KB source. |

### Asset licensing (verified)
- **Code/engine:** MIT (both projects).
- **Character sprites:** the underlying pack
  https://jik-a-4.itch.io/metrocity-free-topdown-character-pack is published on
  itch.io under **Creative Commons Zero v1.0 Universal (CC0 1.0)** — confirmed by
  the itch.io asset-license field and the author's own statements ("free … use as
  you wish", commercial use allowed, credit appreciated not required).
- **Conclusion:** the character sheets may be bundled with attribution. Credits are
  kept in [`../NOTICE.md`](../NOTICE.md) regardless.

## 2. What this branch actually builds

`web/pixel/` — a compact, dependency-free Canvas2D office:

- reuses the **real** upstream character sheets (`char_0..5.png`) and the wall
  tile sheet (`walls.png`); sprite-sheet format (16×32 frames, 7 per row, rows =
  down/up/right) taken from the upstream loader;
- one desk per **recent** actor from the existing sanitized `/api/office`
  endpoint (recency-filtered, capped at 8), characters seated at their desk and
  typing only while the actor's state is `active`;
- friendly labels (`Session N` / `Subagent N`) — never hashes;
- a global "in-flight turns / API runs" line, never a per-character running claim;
- served by the existing token-guarded server (no new server, no auth change);
- demo mode with synthetic fixtures for safe screenshots.

## 3. Honest visual comparison

Captured locally at 1440×900 (demo data):

| | Pixel Agents (upstream, MIT) | `web/pixel` (this branch) |
|---|---|---|
| Room | furnished: wooden desks **with chairs**, bookcases, plants, wall art, varied floor colours, two rooms | sparse: six identical desks in two rows, plain checkerboard floor |
| Density/polish | busy, designed, varied | repetitive, minimal |
| Furniture system | full catalog + layout editor + external packs | none (desk only) |
| Pathfinding | BFS over the tile map | straight-line interpolation |
| Sub-agents / areas | modelled | labels only |

**Verdict: the prototype does not match the upstream look.** It proves the data
path (sanitized actors → per-session desks → seated pixel characters with
friendly labels) but it is visually far behind, exactly as the brief anticipated.

## 4. Why not simply "use the upstream renderer" here

The upstream look comes from a designed `default-layout.json` (21×21 room, 56
placed furniture items, per-tile colours) plus a furniture catalog whose sprites
are **defined in code**, not shipped as PNGs. Faithfully reproducing that means
running the real renderer:

- **Official repo:** add a Hermes `HookProvider` subdirectory, then run the
  upstream standalone server. Largest surface, most faithful, but pulls in the
  full monorepo + its build and its own server (which must *not* be exposed on the
  tailnet without our token layer).
- **Web port (smaller):** vendor the React/Vite app (~178 npm packages) and replace
  its demo spawner with a bridge that reads our sanitized `/api/office`. This keeps
  the real renderer/layout engine and is the **recommended path**; it is a real
  integration task (build step + data-bridge wiring + tests), not a quick port.

Estimated effort for the recommended path: **≈2–4 h** to a reviewable PR
(vendor + bridge + build + tests + screenshots), assuming no upstream API drift.

## 5. Recommendation

1. Do **not** ship `web/pixel` as the redesign — it is a feasibility prototype.
2. Ship the redesign by vendoring the **web port renderer** and feeding it from
   the existing sanitized `/api/office` (same token login, loopback, Tailscale
   Serve private-only). Keep our server as the only exposed surface; never expose
   the upstream standalone server directly.
3. Preserve recency-only filtering, friendly labels, and the "no per-session
   running claim" rule on top of the real renderer.
