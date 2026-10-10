/*
 * Hermes Office — Pixel proof-of-concept.
 *
 * A compact top-down pixel office that reuses the REAL Pixel Agents character
 * sprites and wall tiles (see NOTICE.md / docs/PIXEL_POC.md):
 *   - sprites: MetroCity pack by JIK-A-4, CC0 1.0
 *   - sheet layout + rendering technique: Pixel Agents (MIT, (c) 2026 Pablo De Lucca)
 * The engine here is a small original Canvas2D implementation (no React, no build).
 *
 * Data comes from the existing sanitized /api/office endpoint: pseudonymous ids,
 * recency-filtered actors, no titles/prompts/paths. Never shows raw ids.
 */
(function () {
  "use strict";

  const TILE = 16;          // world pixels per tile
  const COLS = 13, ROWS = 9; // compact room
  const WORLD_W = COLS * TILE;
  const WORLD_H = ROWS * TILE + 24;
  const CHAR_N = 6;          // upstream ships char_0..char_5

  // character sheet: 7 frames of 16x32 per row; rows = down, up, right
  const FRAME_W = 16, FRAME_H = 32, FRAMES = 7;
  const DIR_ROW = { down: 0, up: 1, right: 2 };

  const WALL_PIECE_W = 16, WALL_PIECE_H = 32, WALL_COLS = 4;
  const WALL_FULL = 15;      // bitmask with all neighbours -> solid wall piece

  const canvas = document.getElementById("c");
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;

  let scale = 3;
  const sheets = [];         // Image per character
  let wallImg = null;
  let actors = [];
  let rigs = new Map();      // actorId -> {actor, slot, x, y, tx, ty, dir, frame, t, label}
  let selected = null;
  let labelSeq = new Map();  // actorId -> "Session N" / "Subagent N"
  let seqS = 0, seqB = 0;

  // 8 desk slots (2 rows x 4) — only the first N are shown, one per actor
  const SLOTS = [];
  [3, 6].forEach((row) => { [2, 5, 8, 11].forEach((col) => SLOTS.push({ col, row })); });

  function loadImage(src) {
    return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
  }
  function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0); }

  function displayName(actor) {
    if (!labelSeq.has(actor.id)) {
      labelSeq.set(actor.id, actor.is_subagent ? "Subagent " + (++seqB) : "Session " + (++seqS));
    }
    return labelSeq.get(actor.id);
  }

  // ---- drawing -----------------------------------------------------------
  function drawFloor() {
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const alt = (r + c) % 2 === 0;
        ctx.fillStyle = alt ? "#3b3350" : "#352e48";
        ctx.fillRect(c * TILE, r * TILE + 16, TILE, TILE);
        if (alt) { ctx.fillStyle = "rgba(255,255,255,.02)"; ctx.fillRect(c * TILE, r * TILE + 16, TILE, 3); }
      }
    }
  }
  function drawWalls() {
    const sx = (WALL_FULL % WALL_COLS) * WALL_PIECE_W;
    const sy = Math.floor(WALL_FULL / WALL_COLS) * WALL_PIECE_H;
    for (let c = 0; c < COLS; c++) {
      if (wallImg) ctx.drawImage(wallImg, sx, sy, WALL_PIECE_W, WALL_PIECE_H, c * TILE, 0, WALL_PIECE_W, WALL_PIECE_H);
    }
    // subtle top shading so the wall reads as solid
    ctx.fillStyle = "rgba(0,0,0,.18)";
    ctx.fillRect(0, 0, WORLD_W, 16);
  }
  function drawDesk(col, row, occupied) {
    const x = col * TILE, y = row * TILE + 16;
    ctx.fillStyle = "#00000055"; ctx.fillRect(x + 1, y + 12, 30, 5);          // shadow
    ctx.fillStyle = "#6b4e0a"; ctx.fillRect(x + 1, y + 2, 30, 12);            // wood frame
    ctx.fillStyle = "#a07828"; ctx.fillRect(x + 2, y + 3, 28, 10);            // surface
    ctx.fillStyle = "#b8922e"; ctx.fillRect(x + 4, y + 5, 24, 6);
    ctx.fillStyle = "#141018"; ctx.fillRect(x + 10, y + 1, 12, 8);            // monitor
    ctx.fillStyle = occupied ? "#4ade80" : "#3b3b4a"; ctx.fillRect(x + 12, y + 3, 8, 4);
    ctx.fillStyle = "#20202c"; ctx.fillRect(x + 13, y + 9, 6, 2);             // stand
  }

  function charFrame(img, dir, frame) {
    const row = DIR_ROW[dir] != null ? DIR_ROW[dir] : 0;
    const col = ((frame % FRAMES) + FRAMES) % FRAMES;
    return { img, sx: col * FRAME_W, sy: row * FRAME_H };
  }

  function drawCharacter(rig) {
    const { img, sx, sy } = charFrame(rig.img, rig.dir, rig.frame);
    const px = Math.round(rig.x - FRAME_W / 2);
    const py = Math.round(rig.y - FRAME_H + 6);
    ctx.save();
    if (rig.dir === "left") { ctx.translate(px + FRAME_W, py); ctx.scale(-1, 1); ctx.drawImage(img, sx, sy, FRAME_W, FRAME_H, 0, 0, FRAME_W, FRAME_H); }
    else { ctx.drawImage(img, sx, sy, FRAME_W, FRAME_H, px, py, FRAME_W, FRAME_H); }
    ctx.restore();
  }

  function drawLabel(rig) {
    const text = rig.label;
    ctx.font = "6px ui-monospace, monospace";
    const w = Math.ceil(ctx.measureText(text).width) + 6;
    const x = Math.round(rig.x - w / 2);
    const y = Math.round(rig.y - FRAME_H - 10);
    ctx.fillStyle = rig.actor.is_subagent ? "#7a5cffcc" : "#171520cc";
    ctx.fillRect(x, y, w, 9);
    ctx.fillStyle = selected === rig.actor.id ? "#ffc857" : "#efe9ff";
    ctx.textBaseline = "middle"; ctx.textAlign = "center";
    ctx.fillText(text, x + w / 2, y + 5);
  }

  // ---- simulation --------------------------------------------------------
  function slotFor(i) { return SLOTS[i % SLOTS.length]; }
  function spawnPoint() { return { x: 6 * TILE + TILE / 2, y: 8 * TILE + 24 }; }

  function applyActors(list) {
    const seen = new Set();
    list.slice(0, SLOTS.length).forEach((a, i) => {
      seen.add(a.id);
      const slot = slotFor(i);
      const tx = slot.col * TILE + TILE;      // sit just below the desk centre
      const ty = slot.row * TILE + 24;
      let rig = rigs.get(a.id);
      if (!rig) {
        // spawn seated at the desk so characters read as "at their workstation"
        rig = { actor: a, img: sheets[hash(a.id) % CHAR_N], x: tx, y: ty, tx, ty,
                dir: "up", frame: 0, t: 0, label: displayName(a), slot };
        rigs.set(a.id, rig);
      }
      rig.actor = a;
      rig.label = displayName(a);
      rig.tx = tx; rig.ty = ty;
    });
    for (const [id, rig] of rigs) if (!seen.has(id)) rigs.delete(id);
    updateStats(list);
  }

  function step(dt) {
    for (const rig of rigs.values()) {
      const dx = rig.tx - rig.x, dy = rig.ty - rig.y;
      const moving = Math.abs(dx) > 0.6 || Math.abs(dy) > 0.6;
      if (moving) {
        const speed = 44 * dt;
        const len = Math.hypot(dx, dy) || 1;
        rig.x += (dx / len) * Math.min(speed, Math.abs(dx));
        rig.y += (dy / len) * Math.min(speed, Math.abs(dy));
        rig.dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
        rig.t += dt; const f = Math.floor(rig.t / 0.15) % 3; rig.frame = f; // walk = frames 0..2
      } else {
        rig.dir = "up";
        if (rig.actor.state === "active") { // typing/reading: alternate sit frames
          rig.t += dt; rig.frame = 3 + (Math.floor(rig.t / 0.34) % 2);
        } else { rig.frame = 0; }
      }
    }
  }

  function render() {
    canvas.width = WORLD_W * scale; canvas.height = WORLD_H * scale;
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = "#12101a"; ctx.fillRect(0, 0, WORLD_W, WORLD_H);
    drawFloor();
    // desks + characters sorted by y for correct overlap
    const order = [...rigs.values()].sort((a, b) => a.y - b.y);
    order.forEach((rig) => drawDesk(rig.slot.col, rig.slot.row, rig.actor.state === "active"));
    order.forEach((rig) => drawCharacter(rig));
    drawWalls();
    order.forEach((rig) => drawLabel(rig));
  }

  let last = 0;
  function loop(ts) {
    const dt = Math.min(0.05, (ts - last) / 1000 || 0); last = ts;
    step(dt); render();
    requestAnimationFrame(loop);
  }

  // ---- status + panel ----------------------------------------------------
  function updateStats(list) {
    document.getElementById("stat-recent").textContent = list.filter((a) => a.state === "active").length;
    document.getElementById("stat-sub").textContent = list.filter((a) => a.is_subagent).length;
  }
  function setStatus(p) {
    document.getElementById("mode").textContent = (p.mode === "demo" ? "DEMO" : "LIVE");
    document.getElementById("mode").className = "badge " + (p.mode === "demo" ? "demo" : "live");
    const g = p.gateway || {};
    document.getElementById("gw").textContent = g.available
      ? `in-flight turns ${g.active_agents || 0} · API runs ${g.active_runs || 0}` : "gateway: n/a";
    document.getElementById("updated").textContent = "updated " + new Date((p.generated_at || 0) * 1000).toLocaleTimeString();
    const warn = document.getElementById("warn");
    if (p.degraded) { warn.textContent = "Live API unreachable — showing nothing rather than inventing characters."; warn.style.display = "block"; }
    else warn.style.display = "none";
  }
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function showPanel(a) {
    selected = a.id;
    document.getElementById("pTitle").textContent = displayName(a);
    const rows = [["State", a.state === "active" ? "Recently active" : a.state], ["Zone", a.zone],
      ["Origin", a.origin], ["Subagent", a.is_subagent ? "yes" : "no"],
      ["Parent", a.parent ? (labelSeq.get(a.parent) || "—") : "—"],
      ["Last active", a.age_sec + "s ago"], ["Duration", Math.max(1, Math.round(a.duration_sec / 60)) + "m"],
      ["Tool calls", a.tools]];
    document.getElementById("pBody").innerHTML = rows.map(([k, v]) => `<div class="kv"><span>${esc(k)}</span><b>${esc(String(v))}</b></div>`).join("");
    document.getElementById("panel").classList.add("open");
  }
  document.getElementById("close").onclick = () => { selected = null; document.getElementById("panel").classList.remove("open"); };

  canvas.addEventListener("click", (e) => {
    const r = canvas.getBoundingClientRect();
    const wx = (e.clientX - r.left) / r.width * WORLD_W;
    const wy = (e.clientY - r.top) / r.height * WORLD_H;
    let best = null, bd = 1e9;
    for (const rig of rigs.values()) {
      const d = Math.hypot(wx - rig.x, wy - (rig.y - 16));
      if (d < 14 && d < bd) { bd = d; best = rig; }
    }
    if (best) showPanel(best.actor); else { selected = null; document.getElementById("panel").classList.remove("open"); }
  });

  // ---- transport ---------------------------------------------------------
  async function poll() {
    try {
      const res = await fetch("/api/office", { cache: "no-store" });
      if (res.status === 401 || res.status === 403) { window.location.href = "/login"; return; }
      if (!res.ok) return;
      const p = await res.json();
      setStatus(p);
      applyActors(p.actors || []);
    } catch (e) { /* transient */ }
  }
  function fit() {
    const vw = window.innerWidth, vh = window.innerHeight;
    const s = Math.min((vw - 24) / WORLD_W, (vh - 90) / WORLD_H);
    scale = Math.max(2, Math.min(6, Math.floor(s)));
    document.body.classList.toggle("mobile", vw < 720);
  }
  window.addEventListener("resize", fit);

  Promise.all([
    ...Array.from({ length: CHAR_N }, (_, i) => loadImage("assets/characters/char_" + i + ".png")),
    loadImage("assets/walls.png"),
  ]).then((imgs) => {
    for (let i = 0; i < CHAR_N; i++) sheets[i] = imgs[i];
    wallImg = imgs[CHAR_N];
    fit();
    poll(); setInterval(poll, 4000);
    requestAnimationFrame(loop);
  }).catch(() => { });

  // test/embed hook (pseudonym ids only)
  window.HermesPixel = { ready: () => sheets.length === CHAR_N && !!wallImg, counts: () => rigs.size,
    labels: () => [...rigs.values()].map((r) => r.label), actorIds: () => [...rigs.keys()] };
})();
