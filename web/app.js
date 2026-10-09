/*
 * Hermes Office 3D — front-end.
 *
 * Reads the sanitized snapshot from GET /api/office and streams updates from
 * GET /events (same-origin SSE). It never sees session ids, titles, prompts,
 * transcripts, paths or the Hermes API key — only pseudonyms and counts.
 *
 * The low-poly avatar rig (torso/shoulders/head/arms with elbow/legs with knee)
 * is adapted from VirtOffice (MIT, (c) 2026 Jhonattan L. Jimenez / OneByJorah);
 * see NOTICE. Everything else — controls, zoning, data binding, mobile layout —
 * is written for this project.
 */
(function () {
  "use strict";

  const STATE_COLOR = {
    active: 0x39d98a,
    idle: 0xffb454,
    stale: 0x7a8496,
    completed: 0x5b8def,
  };
  const STATE_LABEL = {
    active: "Active",
    idle: "Idle",
    stale: "Stale",
    completed: "Completed",
  };
  const ZONE_LABEL = {
    desk: "Workstation",
    meeting: "Collab corner",
    lounge: "Lounge",
    booth: "Quiet booth",
    exit: "Archive",
  };

  // ---- office layout -------------------------------------------------------
  const ROOM = { w: 44, d: 30 };

  function zoneSlots(zone, index, count) {
    // deterministic, tidy placement per zone; index wraps into rows
    if (zone === "desk") {
      const col = index % 6, row = Math.floor(index / 6);
      return { x: -15 + col * 3.2, z: -8 + row * 3.0, rot: 0 };
    }
    if (zone === "meeting") {
      const a = (index / Math.max(4, count)) * Math.PI * 2;
      return { x: 9 + Math.cos(a) * 2.4, z: 2 + Math.sin(a) * 2.4, rot: -a };
    }
    if (zone === "lounge") {
      const col = index % 4, row = Math.floor(index / 4);
      return { x: -14 + col * 3.0, z: 9 + row * 2.6, rot: Math.PI };
    }
    if (zone === "booth") {
      return { x: 15 + (index % 2) * 2.4, z: -10 + Math.floor(index / 2) * 2.6, rot: -Math.PI / 2 };
    }
    // exit / archive
    return { x: 17, z: 11 + (index % 6) * 1.4, rot: Math.PI * 0.75 };
  }

  // ---- globals -------------------------------------------------------------
  let scene, camera, renderer, raycaster, clock;
  const rigs = new Map();      // id -> {group, parts, actor, slot}
  const pickable = [];
  let selectedId = null;
  let labelsVisible = true;
  let autoRotate = true;
  const labelSprites = [];

  // orbit state
  const cam = { theta: -Math.PI / 3, phi: 0.95, radius: 34, target: new THREE.Vector3(0, 0, 0), minR: 14, maxR: 70 };
  const pointers = new Map();
  let pinchStart = 0, pinchRadius = 0;

  // ---- three.js bootstrap --------------------------------------------------
  function init() {
    clock = new THREE.Clock();
    raycaster = new THREE.Raycaster();

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0c0f1a);
    scene.fog = new THREE.Fog(0x0c0f1a, 42, 92);

    camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 500);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    const small = Math.min(window.innerWidth, window.innerHeight) < 720;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, small ? 1.5 : 2));
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.shadowMap.enabled = !small;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    document.getElementById("stage").appendChild(renderer.domElement);

    buildLighting();
    buildRoom();
    buildFurniture();

    bindControls();
    window.addEventListener("resize", onResize);
    renderer.domElement.addEventListener("pointerdown", onPickDown);

    document.getElementById("zoomIn").onclick = () => { cam.radius = Math.max(cam.minR, cam.radius - 3); };
    document.getElementById("zoomOut").onclick = () => { cam.radius = Math.min(cam.maxR, cam.radius + 3); };
    document.getElementById("reset").onclick = () => { cam.theta = -Math.PI / 3; cam.phi = 0.95; cam.radius = 34; };
    document.getElementById("rotate").onclick = (e) => { autoRotate = !autoRotate; e.currentTarget.classList.toggle("on", autoRotate); };
    document.getElementById("labels").onclick = (e) => {
      labelsVisible = !labelsVisible;
      labelSprites.forEach((s) => (s.visible = labelsVisible));
      e.currentTarget.classList.toggle("on", labelsVisible);
    };
    document.getElementById("rotate").classList.toggle("on", autoRotate);
    document.getElementById("labels").classList.toggle("on", labelsVisible);
    document.getElementById("detailClose").onclick = () => select(null);

    onResize();
    refreshConfig();
    connect();
    animate();
  }

  function buildLighting() {
    scene.add(new THREE.HemisphereLight(0x8fb2ff, 0x20202c, 0.75));
    const key = new THREE.DirectionalLight(0xffffff, 0.9);
    key.position.set(-18, 26, 14);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.left = -30; key.shadow.camera.right = 30;
    key.shadow.camera.top = 30; key.shadow.camera.bottom = -30;
    scene.add(key);
    const warm = new THREE.PointLight(0xffb35c, 0.5, 40);
    warm.position.set(10, 6, 6);
    scene.add(warm);
  }

  function box(w, h, d, color, opts) {
    const o = opts || {};
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(w, h, d),
      new THREE.MeshStandardMaterial({ color: color, roughness: o.rough == null ? 0.7 : o.rough, metalness: o.metal || 0 })
    );
    mesh.position.set(o.x || 0, o.y || 0, o.z || 0);
    if (o.rot) mesh.rotation.y = o.rot;
    mesh.castShadow = !!o.shadow;
    mesh.receiveShadow = true;
    scene.add(mesh);
    return mesh;
  }

  function buildRoom() {
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(ROOM.w, ROOM.d),
      new THREE.MeshStandardMaterial({ color: 0x1a2030, roughness: 0.95 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    // accent rug marking the collab corner
    const rug = new THREE.Mesh(
      new THREE.CircleGeometry(4.2, 40),
      new THREE.MeshStandardMaterial({ color: 0x24304a, roughness: 1 })
    );
    rug.rotation.x = -Math.PI / 2; rug.position.set(9, 0.01, 2); scene.add(rug);

    const wallMat = 0x2a3350;
    box(ROOM.w, 4, 0.3, wallMat, { y: 2, z: -ROOM.d / 2, shadow: true });
    box(ROOM.w, 4, 0.3, wallMat, { y: 2, z: ROOM.d / 2, shadow: true });
    box(0.3, 4, ROOM.d, wallMat, { x: -ROOM.w / 2, y: 2, shadow: true });
    box(0.3, 4, ROOM.d, wallMat, { x: ROOM.w / 2, y: 2, shadow: true });
  }

  function workstation(x, z) {
    box(2.0, 0.08, 1.0, 0x6b7280, { x: x, y: 0.75, z: z, shadow: true });      // desk top
    box(0.08, 0.75, 0.08, 0x4b5563, { x: x - 0.9, y: 0.37, z: z - 0.4 });
    box(0.08, 0.75, 0.08, 0x4b5563, { x: x + 0.9, y: 0.37, z: z - 0.4 });
    box(0.08, 0.75, 0.08, 0x4b5563, { x: x - 0.9, y: 0.37, z: z + 0.4 });
    box(0.08, 0.75, 0.08, 0x4b5563, { x: x + 0.9, y: 0.37, z: z + 0.4 });
    box(0.62, 0.38, 0.05, 0x111827, { x: x, y: 1.0, z: z - 0.35 });           // monitor
    box(0.16, 0.02, 0.1, 0x9ca3af, { x: x, y: 0.8, z: z + 0.18 });            // keyboard
    box(0.4, 0.42, 0.4, 0x374151, { x: x, y: 0.21, z: z + 0.75, shadow: true }); // chair seat
    box(0.4, 0.5, 0.06, 0x374151, { x: x, y: 0.45, z: z + 0.95 });
  }

  function meetingTable(cx, cz) {
    const top = new THREE.Mesh(
      new THREE.CylinderGeometry(2.0, 2.0, 0.12, 32),
      new THREE.MeshStandardMaterial({ color: 0x8b5cf6, roughness: 0.5 })
    );
    top.position.set(cx, 0.75, cz); top.castShadow = true; top.receiveShadow = true; scene.add(top);
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.3, 0.75, 16),
      new THREE.MeshStandardMaterial({ color: 0x374151 }));
    leg.position.set(cx, 0.37, cz); scene.add(leg);
  }

  function sofa(x, z) {
    box(2.4, 0.4, 0.9, 0x4b5563, { x: x, y: 0.35, z: z, shadow: true });
    box(2.4, 0.5, 0.25, 0x4b5563, { x: x, y: 0.7, z: z - 0.33 });
    box(0.18, 0.55, 0.9, 0x4b5563, { x: x - 1.2, y: 0.5, z: z });
    box(0.18, 0.55, 0.9, 0x4b5563, { x: x + 1.2, y: 0.5, z: z });
  }

  function booth(x, z) {
    box(1.3, 2.4, 1.3, 0x7f1d1d, { x: x, y: 1.2, z: z, shadow: true });
    box(1.36, 0.12, 1.36, 0x991b1b, { x: x, y: 2.45, z: z });
  }

  function plant(x, z) {
    const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.26, 0.32, 0.4, 12),
      new THREE.MeshStandardMaterial({ color: 0x6b4f3a }));
    pot.position.set(x, 0.2, z); pot.castShadow = true; scene.add(pot);
    const leafMat = new THREE.MeshStandardMaterial({ color: 0x2f9e6e, roughness: 0.9 });
    const leaves = new THREE.Mesh(new THREE.IcosahedronGeometry(0.55, 0), leafMat);
    leaves.position.set(x, 0.9, z); leaves.castShadow = true; scene.add(leaves);
  }

  function buildFurniture() {
    for (let i = 0; i < 6; i++) workstation(-15 + i * 3.2, -7.6);
    for (let i = 0; i < 6; i++) workstation(-15 + i * 3.2, -4.6);
    meetingTable(9, 2);
    sofa(-13, 11); sofa(-9, 11);
    booth(16, -9); booth(18.4, -9); booth(16, -6.4); booth(18.4, -6.4);
    plant(-20, -13); plant(20, 13); plant(-20, 13); plant(20, -13); plant(2, 13);
  }

  // ---- avatar rig (adapted from VirtOffice, MIT) ---------------------------
  function buildAvatar(colorHex) {
    const group = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({ color: colorHex, roughness: 0.55 });
    const dark = new THREE.MeshStandardMaterial({ color: 0x2a2a35, roughness: 0.7 });
    const skin = new THREE.MeshStandardMaterial({ color: 0xf0d0b0, roughness: 0.6 });
    const parts = {};

    const body = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.58, 0.28), mat);
    body.position.y = 0.87; body.castShadow = true; group.add(body);
    const shoulders = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.12, 0.3), mat);
    shoulders.position.y = 1.12; group.add(shoulders);
    const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.08, 0.1, 8), skin);
    neck.position.y = 1.22; group.add(neck);
    const head = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.32, 0.3), skin);
    head.position.y = 1.42; head.castShadow = true; group.add(head);
    const hair = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.13, 0.32),
      new THREE.MeshStandardMaterial({ color: 0x1f2233, roughness: 0.9 }));
    hair.position.y = 1.57; group.add(hair);
    const eyeMat = new THREE.MeshBasicMaterial({ color: 0x11121f });
    [-0.08, 0.08].forEach((ex) => {
      const eye = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 8), eyeMat);
      eye.position.set(ex, 1.44, 0.15); group.add(eye);
    });

    function arm(side) {
      const g = new THREE.Group();
      const upper = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.28, 0.1), mat);
      upper.position.y = -0.14; g.add(upper);
      const lower = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.25, 0.09), mat);
      lower.position.y = -0.38; g.add(lower);
      g.position.set(side * 0.30, 1.08, 0);
      group.add(g);
      return g;
    }
    parts.leftArm = arm(-1);
    parts.rightArm = arm(1);

    function leg(side) {
      const g = new THREE.Group();
      const upper = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.28, 0.16), dark);
      upper.position.y = -0.14; g.add(upper);
      const lower = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.24, 0.14), dark);
      lower.position.y = -0.38; g.add(lower);
      g.position.set(side * 0.12, 0.5, 0);
      group.add(g);
      return g;
    }
    parts.leftLeg = leg(-1);
    parts.rightLeg = leg(1);

    // subagent halo ring — toggled on when the actor is a subagent
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.34, 0.44, 24),
      new THREE.MeshBasicMaterial({ color: 0xfacc15, side: THREE.DoubleSide, transparent: true, opacity: 0.85 })
    );
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.02; ring.visible = false;
    group.add(ring);
    parts.ring = ring;
    parts.material = mat;  // shared by torso/shoulders/arms — recolour on state change

    return { group: group, parts: parts };
  }

  function makeLabel(text, colorHex) {
    const canvas = document.createElement("canvas");
    canvas.width = 256; canvas.height = 64;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "rgba(10,12,20,0.82)";
    roundRect(ctx, 2, 2, 252, 60, 14); ctx.fill();
    ctx.strokeStyle = "#" + colorHex.toString(16).padStart(6, "0");
    ctx.lineWidth = 3; ctx.stroke();
    ctx.fillStyle = "#e8ecf5"; ctx.font = "bold 30px system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(text, 128, 34);
    const tex = new THREE.CanvasTexture(canvas);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }));
    sprite.scale.set(2.6, 0.65, 1);
    return sprite;
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // ---- data binding --------------------------------------------------------
  function applyPayload(payload) {
    if (!payload || !Array.isArray(payload.actors)) return;
    const actors = payload.actors;
    const seen = new Set();

    const zoneCounts = {};
    actors.forEach((a) => (zoneCounts[a.zone] = (zoneCounts[a.zone] || 0) + 1));
    const zoneIndex = {};

    actors.forEach((actor) => {
      seen.add(actor.id);
      const zi = (zoneIndex[actor.zone] = (zoneIndex[actor.zone] || 0) + 1) - 1;
      const slot = zoneSlots(actor.zone, zi, zoneCounts[actor.zone]);

      let rig = rigs.get(actor.id);
      if (!rig) {
        const colour = STATE_COLOR[actor.state] || 0x8892a6;
        const { group, parts } = buildAvatar(colour);
        group.position.set(slot.x, 0, slot.z);
        scene.add(group);
        const label = makeLabel(actor.id, colour);
        label.position.set(0, 2.15, 0);
        group.add(label);
        labelSprites.push(label);
        rig = {
          group: group, parts: parts, label: label, actor: actor,
          cur: group.position.clone(), slot: slot,
          target: new THREE.Vector3(slot.x, 0, slot.z), state: actor.state,
        };
        rig.group.userData.actorId = actor.id;
        pickable.push(rig.group);
        rigs.set(actor.id, rig);
      }
      rig.actor = actor;
      rig.slot = slot;
      rig.target.set(slot.x, 0, slot.z);
      if (rig.state !== actor.state) {
        // keep the avatar's colour honestly in sync with the observable state
        rig.parts.material.color.setHex(STATE_COLOR[actor.state] || 0x8892a6);
        rig.state = actor.state;
      }
      rig.parts.ring.visible = !!actor.is_subagent;
      updateLabel(rig);
    });

    // remove actors that disappeared
    rigs.forEach((rig, id) => {
      if (!seen.has(id)) {
        scene.remove(rig.group);
        const li = labelSprites.indexOf(rig.label);
        if (li >= 0) labelSprites.splice(li, 1);
        const pi = pickable.indexOf(rig.group);
        if (pi >= 0) pickable.splice(pi, 1);
        rigs.delete(id);
      }
    });

    updateStatus(payload);
    if (selectedId && rigs.has(selectedId)) showDetail(rigs.get(selectedId).actor);
  }

  function updateLabel(rig) {
    const a = rig.actor;
    const short = a.id.replace(/^s-/, "");
    const text = (a.state === "completed" ? "✔ " : "") + short;
    const canvas = rig.label.material.map.image;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "rgba(10,12,20,0.82)";
    roundRect(ctx, 2, 2, 252, 60, 14); ctx.fill();
    ctx.strokeStyle = "#" + (STATE_COLOR[a.state] || 0x8892a6).toString(16).padStart(6, "0");
    ctx.lineWidth = 3; ctx.stroke();
    ctx.fillStyle = "#e8ecf5"; ctx.font = "bold 30px system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(text, 128, 34);
    rig.label.material.map.needsUpdate = true;
  }

  function updateStatus(p) {
    const s = p.summary || {};
    const g = p.gateway || {};
    document.getElementById("stat-active").textContent = s.active || 0;
    document.getElementById("stat-sub").textContent = s.subagents || 0;
    document.getElementById("stat-idle").textContent = s.idle || 0;
    document.getElementById("stat-stale").textContent = s.stale || 0;
    document.getElementById("stat-done").textContent = s.completed || 0;

    const badge = document.getElementById("mode");
    badge.textContent = p.mode === "demo" ? "DEMO" : "LIVE";
    badge.className = "badge " + (p.mode === "demo" ? "demo" : "live");

    const warn = document.getElementById("warn");
    if (p.degraded) {
      warn.textContent = "Live API unreachable — showing an empty snapshot.";
      warn.style.display = "block";
    } else {
      warn.style.display = "none";
    }

    const gtxt = g.available
      ? `runs ${g.active_runs} · agents ${g.active_agents}${g.busy ? " · busy" : ""}`
      : "gateway: n/a";
    document.getElementById("gw").textContent = gtxt;
    document.getElementById("updated").textContent =
      "updated " + new Date((p.generated_at || 0) * 1000).toLocaleTimeString();
  }

  // ---- details panel (sanitized fields only) -------------------------------
  function select(id) {
    selectedId = id;
    const panel = document.getElementById("detail");
    if (!id || !rigs.has(id)) { panel.classList.remove("open"); return; }
    showDetail(rigs.get(id).actor);
    panel.classList.add("open");
  }

  function showDetail(a) {
    const rows = [
      ["State", STATE_LABEL[a.state] || a.state],
      ["Zone", ZONE_LABEL[a.zone] || a.zone],
      ["Origin", a.origin],
      ["Subagent", a.is_subagent ? "yes" : "no"],
      ["Parent", a.parent ? a.parent.replace(/^s-/, "") : "—"],
      ["Last active", fmtAge(a.age_sec) + " ago"],
      ["Duration", fmtDur(a.duration_sec)],
      ["Tool calls", a.tools],
      ["Turns", a.turns],
      ["Activity", Math.round((a.activity || 0) * 100) + "%"],
      ["Pseudonym", a.id],
    ];
    document.getElementById("detailBody").innerHTML = rows
      .map(([k, v]) => `<div class="kv"><span>${esc(k)}</span><b>${esc(String(v))}</b></div>`)
      .join("");
    document.getElementById("detailTitle").textContent = a.id.replace(/^s-/, "");
  }

  function fmtAge(s) {
    if (s < 60) return s + "s";
    if (s < 3600) return Math.floor(s / 60) + "m";
    return Math.floor(s / 3600) + "h";
  }
  function fmtDur(s) {
    const m = Math.floor(s / 60);
    if (m < 60) return m + "m";
    return Math.floor(m / 60) + "h " + (m % 60) + "m";
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ---- controls (mouse + touch orbit) --------------------------------------
  function bindControls() {
    const el = renderer.domElement;
    el.style.touchAction = "none";
    el.addEventListener("pointerdown", (e) => {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      el.setPointerCapture(e.pointerId);
      if (pointers.size === 2) {
        const pts = [...pointers.values()];
        pinchStart = dist(pts[0], pts[1]);
        pinchRadius = cam.radius;
      }
    });
    el.addEventListener("pointermove", (e) => {
      const prev = pointers.get(e.pointerId);
      if (!prev) return;
      const dx = e.clientX - prev.x, dy = e.clientY - prev.y;
      prev.x = e.clientX; prev.y = e.clientY;
      if (pointers.size === 1) {
        cam.theta -= dx * 0.006;
        cam.phi = clamp(cam.phi - dy * 0.005, 0.25, 1.45);
      } else if (pointers.size === 2) {
        const pts = [...pointers.values()];
        const d = dist(pts[0], pts[1]);
        if (pinchStart > 0) cam.radius = clamp(pinchRadius * (pinchStart / d), cam.minR, cam.maxR);
      }
    });
    const up = (e) => { pointers.delete(e.pointerId); if (pointers.size < 2) pinchStart = 0; };
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
    el.addEventListener("wheel", (e) => {
      e.preventDefault();
      cam.radius = clamp(cam.radius + Math.sign(e.deltaY) * 2.5, cam.minR, cam.maxR);
    }, { passive: false });
  }

  function onPickDown(e) {
    const startX = e.clientX, startY = e.clientY;
    const el = renderer.domElement;
    const handler = (ev) => {
      el.removeEventListener("pointerup", handler);
      el.removeEventListener("pointercancel", handler);
      if (Math.abs(ev.clientX - startX) > 5 || Math.abs(ev.clientY - startY) > 5) return;
      const rect = el.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((ev.clientX - rect.left) / rect.width) * 2 - 1,
        -((ev.clientY - rect.top) / rect.height) * 2 + 1
      );
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObjects(pickable, true);
      if (hits.length) {
        let o = hits[0].object;
        while (o && !o.userData.actorId) o = o.parent;
        if (o) select(o.userData.actorId);
      } else {
        select(null);
      }
    };
    el.addEventListener("pointerup", handler);
    el.addEventListener("pointercancel", handler);
  }

  function dist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  // ---- frame loop ----------------------------------------------------------
  function updateCamera(dt) {
    if (autoRotate && pointers.size === 0) cam.theta += dt * 0.06;
    const r = cam.radius;
    const x = cam.target.x + r * Math.sin(cam.phi) * Math.sin(cam.theta);
    const y = cam.target.y + r * Math.cos(cam.phi);
    const z = cam.target.z + r * Math.sin(cam.phi) * Math.cos(cam.theta);
    camera.position.set(x, y, z);
    camera.lookAt(cam.target);
  }

  function animate() {
    requestAnimationFrame(animate);
    const dt = Math.min(0.05, clock.getDelta());
    const t = clock.elapsedTime;
    updateCamera(dt);

    rigs.forEach((rig) => {
      const a = rig.actor;
      // walk toward the assigned slot
      rig.cur.x += (rig.target.x - rig.cur.x) * Math.min(1, dt * 2.5);
      rig.cur.z += (rig.target.z - rig.cur.z) * Math.min(1, dt * 2.5);
      rig.group.position.set(rig.cur.x, 0, rig.cur.z);
      const moving = Math.hypot(rig.target.x - rig.cur.x, rig.target.z - rig.cur.z) > 0.05;
      if (moving) rig.group.rotation.y = Math.atan2(rig.target.x - rig.cur.x, rig.target.z - rig.cur.z);
      else if (rig.slot.rot != null) rig.group.rotation.y = rig.slot.rot;

      // idle bob + state-driven arm motion
      const speed = a.state === "active" ? 1 : a.state === "idle" ? 0.5 : a.state === "stale" ? 0.25 : 0;
      rig.group.position.y = Math.sin(t * 2 * (0.6 + speed)) * 0.02 * (0.4 + speed);
      if (a.state === "active") {
        const beat = Math.sin(t * 9) * 0.5 + 0.5;
        rig.parts.leftArm.rotation.x = -0.7 - beat * 0.5;
        rig.parts.rightArm.rotation.x = -0.7 - (1 - beat) * 0.5;
      } else if (moving) {
        const swing = Math.sin(t * 8) * 0.5;
        rig.parts.leftArm.rotation.x = swing;
        rig.parts.rightArm.rotation.x = -swing;
        rig.parts.leftLeg.rotation.x = -swing * 0.7;
        rig.parts.rightLeg.rotation.x = swing * 0.7;
      } else {
        rig.parts.leftArm.rotation.x *= 0.9;
        rig.parts.rightArm.rotation.x *= 0.9;
        rig.parts.leftLeg.rotation.x *= 0.9;
        rig.parts.rightLeg.rotation.x *= 0.9;
      }
      if (a.state === "completed") rig.group.traverse((n) => { if (n.material && n.material.opacity != null) { n.material.transparent = true; n.material.opacity = 0.55; } });

      if (rig.label) rig.label.visible = labelsVisible;
    });

    renderer.render(scene, camera);
  }

  function onResize() {
    const w = window.innerWidth, h = window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    document.body.classList.toggle("mobile", w < 720);
  }

  // ---- transport -----------------------------------------------------------
  let pollTimer = null;
  async function fetchOnce() {
    try {
      const res = await fetch("/api/office", { cache: "no-store" });
      if (res.status === 401 || res.status === 403) { window.location.href = "/login"; return; }
      if (!res.ok) return;
      applyPayload(await res.json());
    } catch (e) { /* transient */ }
  }

  async function refreshConfig() {
    try {
      const res = await fetch("/api/config", { cache: "no-store" });
      if (res.ok) {
        const cfg = await res.json();
        window.__POLL_MS__ = (cfg.poll_seconds || 4) * 1000;
      }
    } catch (e) { /* ignore */ }
  }

  function connect() {
    fetchOnce();
    let es;
    try {
      es = new EventSource("/events");
      es.onmessage = (ev) => {
        try { applyPayload(JSON.parse(ev.data)); } catch (e) { /* ignore */ }
      };
      es.onerror = () => {
        es.close();
        if (!pollTimer) pollTimer = setInterval(fetchOnce, window.__POLL_MS__ || 4000);
      };
      es.onopen = () => { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } };
    } catch (e) {
      pollTimer = setInterval(fetchOnce, 4000);
    }
    // refresh when the tab/app returns to the foreground (mobile especially)
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && !pollTimer) fetchOnce();
    });
  }

  window.addEventListener("DOMContentLoaded", init);

  // Minimal read-only extension point (pseudonym ids only — no session data).
  // Handy for automated tests and for embedders that want to drive selection.
  window.HermesOffice = {
    version: "0.1.0",
    ready: () => !!renderer,
    actorIds: () => Array.from(rigs.keys()),
    counts: () => rigs.size,
    select: (id) => select(id),
    selected: () => selectedId,
  };
})();
