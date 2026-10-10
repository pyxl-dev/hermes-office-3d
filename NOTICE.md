# Notices and third-party attribution

Hermes Office 3D is MIT-licensed (see `LICENSE`). It builds on and includes
work by others; those parts keep their own copyright and license.

## Bundled / adapted code

### VirtOffice — MIT
- Source: https://github.com/OneByJorah/VirtOffice
- Copyright (c) 2026 Jhonattan L. Jimenez (OneByJorah / JorahOne Networks)
- What we use: the low-poly humanoid avatar rig in `web/app.js`
  (`buildAvatar`) — torso, shoulders, neck, head, hair, eyes, two-segment arms
  with hands, and two-segment legs — is adapted from VirtOffice's single-file
  Three.js office. The idea of mapping agents to characters that occupy office
  zones also follows VirtOffice's design.
- License text: MIT (same terms as this project's `LICENSE`).

### three.js r128 — MIT
- Source: https://threejs.org / https://github.com/mrdoob/three.js
- Copyright 2010-2021 Three.js Authors
- Vendored verbatim at `web/vendor/three.min.js` so the office runs offline
  (no CDN, no third-party network calls at runtime).

### Pixel Agents — MIT (audit + bundled sprites for the pixel POC)
- Source: https://github.com/pixel-agents-hq/pixel-agents (commit `d1e007a`, v1.4.1)
- Copyright (c) 2026 Pablo De Lucca — MIT.
- What we use: the **character sprite sheets** (`web/pixel/assets/characters/char_0..5.png`)
  and the **wall tile sheet** (`web/pixel/assets/walls.png`), plus the sprite-sheet
  layout knowledge (frames 16×32, 7 per row, rows = down/up/right) taken from the
  upstream loader. The pixel POC engine in `web/pixel/pixel.js` is a small original
  Canvas2D implementation, not a copy of the upstream renderer.
- Note: `web/pixel/` is a **visual feasibility prototype**, not a Pixel Agents
  equivalent — see [`docs/PIXEL_POC.md`](docs/PIXEL_POC.md).

### MetroCity character sprites — CC0 1.0
- Source: https://jik-a-4.itch.io/metrocity-free-topdown-character-pack (JIK-A-4)
- License: **Creative Commons Zero v1.0 Universal** (public domain). Redistribution,
  modification and commercial use are permitted; credit is appreciated, not required.
- These are the sprites inside the Pixel Agents character sheets above.

## Inspected but NOT included

### Hermes3D — MIT
- Source: https://github.com/iamlukethedev/Hermes3D
- Copyright (c) 2026 Luke The Dev
- Evaluated as a possible base and deliberately **not** reused: it is a large
  Next.js 16 + React Three Fiber + Phaser application with a Node WebSocket
  proxy, a Spotify integration and a voice/standup surface — far more surface
  area than this read-only MVP needs. No code or assets were taken from it.
