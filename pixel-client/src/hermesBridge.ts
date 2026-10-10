/**
 * Hermes bridge — replaces the demo spawner with REAL, sanitized observability.
 *
 * It reads the existing `/api/office` payload (pseudonymous ids, recency-filtered
 * actors, no titles/prompts/paths) and creates/removes characters accordingly.
 *
 * Honesty rules baked in here:
 *  - LIVE mode never fabricates tool activity. We only tell the renderer a
 *    character is "active" (recently seen) or idle. We do NOT send toolStart
 *    events, so no character is animated as "writing code right now" purely
 *    because `last_active < 120s`.
 *  - Characters are labelled "Session N" / "Subagent N" — never raw ids.
 *  - Max 8 characters (one per recent session), so no historic crowd.
 */

import { postToWebview, onWebviewMessage } from './vscodeApi.js'
import {
  loadCharacterSprites,
  loadWallSprites,
  loadFloorSprites,
  loadFurnitureAssets,
  loadDefaultLayout,
} from './browserAssetLoader.js'

const MAX_AGENTS = 8
const POLL_MS = 4000

const idByActor = new Map<string, number>() // pseudonym -> numeric renderer id
const nameByActor = new Map<string, string>()
let nextId = 0
let seqSession = 0
let seqSubagent = 0

function friendlyName(actor: { id: string; is_subagent?: boolean }): string {
  const existing = nameByActor.get(actor.id)
  if (existing) return existing
  const name = actor.is_subagent ? `Subagent ${++seqSubagent}` : `Session ${++seqSession}`
  nameByActor.set(actor.id, name)
  return name
}

function setBadge(mode: string): void {
  let el = document.getElementById('hermes-mode-badge')
  if (!el) {
    el = document.createElement('div')
    el.id = 'hermes-mode-badge'
    el.style.cssText =
      'position:fixed;top:8px;left:8px;z-index:9999;font:700 11px ui-monospace,monospace;' +
      'padding:3px 8px;border-radius:4px;letter-spacing:.5px'
    document.body.appendChild(el)
  }
  const demo = mode === 'demo'
  el.textContent = demo ? 'DEMO' : 'LIVE'
  el.style.background = demo ? '#ffc857' : '#4ade80'
  el.style.color = demo ? '#241c06' : '#08210f'
}

async function handleReady(): Promise<void> {
  try {
    postToWebview({ type: 'settingsLoaded', soundEnabled: false })
  } catch { /* ignore */ }

  try {
    postToWebview({ type: 'characterSpritesLoaded', characters: await loadCharacterSprites() })
  } catch { /* ignore */ }

  try {
    const floors = await loadFloorSprites()
    if (floors.length) postToWebview({ type: 'floorTilesLoaded', sprites: floors })
  } catch { /* ignore */ }

  try {
    const walls = await loadWallSprites()
    if (walls.length) postToWebview({ type: 'wallTilesLoaded', sprites: walls })
  } catch { /* ignore */ }

  // The furnished room: load the layout ALWAYS (independent of the catalog), so a
  // missing furniture catalog can never silently downgrade the office.
  let layout: Record<string, unknown> | null = null
  try {
    const assets = await loadFurnitureAssets()
    if (assets) {
      postToWebview({ type: 'furnitureAssetsLoaded', catalog: assets.catalog, sprites: assets.sprites })
    }
    layout = await loadDefaultLayout()
  } catch { /* ignore */ }
  postToWebview({ type: 'layoutLoaded', layout })
}

function applyPayload(payload: { mode?: string; actors?: Array<Record<string, unknown>> }): void {
  const actors = (payload.actors || []).slice(0, MAX_AGENTS)
  setBadge(payload.mode || 'live')

  const seen = new Set<string>()
  for (const actor of actors) {
    const pid = String(actor.id || '')
    if (!pid) continue
    seen.add(pid)
    let id = idByActor.get(pid)
    if (id === undefined) {
      id = ++nextId
      idByActor.set(pid, id)
      postToWebview({ type: 'agentCreated', id, folderName: friendlyName(actor as { id: string; is_subagent?: boolean }) })
    }
    // Neutral only: we have no per-conversation tool events, so we never claim a
    // character is "coding right now". Recency is surfaced in the header badge.
    postToWebview({ type: 'agentStatus', id, status: 'idle' })
  }

  for (const [pid, id] of [...idByActor.entries()]) {
    if (!seen.has(pid)) {
      postToWebview({ type: 'agentClosed', id })
      idByActor.delete(pid)
      nameByActor.delete(pid)
    }
  }
}

async function poll(): Promise<void> {
  try {
    const res = await fetch('/api/office', { cache: 'no-store' })
    if (res.status === 401 || res.status === 403) {
      window.location.href = '/login'
      return
    }
    if (!res.ok) return
    applyPayload(await res.json())
  } catch { /* transient */ }
}

/**
 * The upstream toolbar offers "+ Agent" (spawn a demo agent) and an Open-Claude
 * flow. In Hermes mode characters come from real sessions, so those controls are
 * inert and must not look clickable. The layout editor is preserved.
 */
function hideInertControls(): void {
  const apply = () => {
    for (const b of Array.from(document.querySelectorAll('button'))) {
      const t = (b.textContent || '').trim().toLowerCase()
      if (t.includes('+ agent') || t.includes('open claude') || t.includes('new agent')) {
        ;(b as HTMLButtonElement).style.display = 'none'
      }
    }
  }
  apply()
  window.setInterval(apply, 1500) // toolbar re-renders; keep them hidden

  // Initial zoom-to-fit: the default zoom leaves the compact room small inside a
  // large dark canvas. Click the zoom-in control a bounded number of times.
  let bumps = 0
  const zoomIn = window.setInterval(() => {
    const plus = Array.from(document.querySelectorAll('button')).find(
      (b) => (b.textContent || '').trim() === '+',
    ) as HTMLButtonElement | undefined
    if (plus && bumps < 3) { plus.click(); bumps++ } else window.clearInterval(zoomIn)
  }, 600)
}

export async function initHermesBridge(): Promise<void> {
  onWebviewMessage(async (msg) => {
    if (msg.type === 'webviewReady') {
      // React is mounted and listening now — load assets, then start feeding it.
      await handleReady()
      await poll()
      window.setInterval(poll, POLL_MS)
      hideInertControls()
    }
    // Clicking an avatar asks the backend to focus that agent. We answer with the
    // sanitized selection event the app expects (no transcript, no raw ids).
    else if (msg.type === 'focusAgent') {
      const id = msg.id as number
      postToWebview({ type: 'agentSelected', id })
      const pid = [...idByActor.entries()].find(([, v]) => v === id)?.[0]
      const name = pid ? nameByActor.get(pid) : undefined
      if (name) document.title = `Hermes Office — ${name}`
    }
    // In Hermes mode the "+ Agent" button is inert: characters reflect real
    // sessions only. Layout edits are kept locally but not persisted upstream.
    else if (msg.type === 'saveLayout') {
      try { localStorage.setItem('hermes-office-layout', JSON.stringify(msg.layout)) } catch { /* ignore */ }
    }
  })

  // read-only test/embed hook (pseudonym-free: counts + renderer ids only)
  ;(window as unknown as Record<string, unknown>).HermesPixelBridge = {
    agents: () => idByActor.size,
    rendererIds: () => [...idByActor.values()],
    names: () => [...nameByActor.values()],
    mode: () => (document.getElementById('hermes-mode-badge') || {}).textContent,
  }
}
