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

let degraded = false
let currentMode: 'live' | 'demo' = 'live'
const toolState = new Map<number, string>()
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
  currentMode = mode === 'demo' ? 'demo' : 'live'
  const demo = mode === 'demo'
  el.textContent = demo ? 'DEMO' : degraded ? 'DISCONNECTED' : 'LIVE'
  el.style.background = demo ? '#ffc857' : degraded ? '#ef4444' : '#4ade80'
  el.style.color = demo ? '#241c06' : degraded ? '#ffffff' : '#08210f'
}

/** Live-but-unreachable API must not be reported as healthy. */
export function setDegraded(value: boolean): void {
  if (value === degraded) return
  degraded = value
  setBadge(currentMode)
}

/** Reviewer P2: the layout saved by the renderer was never loaded back. */
function restoreSavedLayout(): void {
  try {
    const raw = localStorage.getItem('hermes-office-layout')
    if (!raw) return
    const layout = JSON.parse(raw) as { cols?: unknown; rows?: unknown; furniture?: unknown }
    if (typeof layout?.cols !== 'number' || typeof layout?.rows !== 'number') return
    if (!Array.isArray(layout?.furniture)) return
    postToWebview({ type: 'layoutLoaded', layout })
  } catch {
    /* corrupt entry: ignore rather than break startup */
  }
}

/** Reviewer P2: Settings import/export have no handler in Hermes mode. */
function hideInertSettings(): void {
  const hide = () => {
    for (const el of Array.from(document.querySelectorAll('button'))) {
      // Only import/export are unimplemented here. Settings and Save stay usable:
      // hiding them would break the layout editor.
      if (/^(import|export)(\s|$)/i.test((el.textContent || '').trim())) {
        el.style.display = 'none'
        el.setAttribute('aria-hidden', 'true')
      }
    }
  }
  hide()
  window.setInterval(hide, 1500)
}

async function fetchPayload(): Promise<void> {
  try {
    const res = await fetch('/api/office', { cache: 'no-store' })
    // Reviewer P2: a degraded (live but unreachable) API must not show healthy.
    try {
      const probe = (await res.clone().json()) as { degraded?: boolean }
      setDegraded(probe?.degraded === true)
    } catch {
      /* keep the last known state */
    }
    if (res.status === 401 || res.status === 403) { window.location.href = '/login'; return }
    if (!res.ok) {
      setDegraded(true)
      return
    }
    const data = (await res.json()) as { degraded?: boolean }
    // Reviewer P2: degraded must be re-evaluated on every poll, not only at startup.
    setDegraded(data?.degraded === true)
    applyPayload(data as unknown as Parameters<typeof applyPayload>[0])
  } catch {
    // Reviewer P2: a network failure must not leave a stale green LIVE badge.
    setDegraded(true)
  }
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

  try {
    const assets = await loadFurnitureAssets()
    if (assets) {
      postToWebview({ type: 'furnitureAssetsLoaded', catalog: assets.catalog, sprites: assets.sprites })
    }
  } catch { /* ignore */ }

  // IMPORTANT ORDERING: emit the agents BEFORE the layout. The renderer buffers
  // agents that arrive before `layoutLoaded` and adds them with
  // `skipSpawnEffect=true`; agents that arrive after are added with the Matrix
  // "materialise" effect, which left them effectively invisible in practice.
  await fetchPayload()

  // The furnished room: load the layout ALWAYS (independent of the catalog), so a
  // missing furniture catalog can never silently downgrade the office.
  let layout: Record<string, unknown> | null = null
  try {
    layout = await loadDefaultLayout()
  } catch { /* ignore */ }
  postToWebview({ type: 'layoutLoaded', layout })
}

function applyPayload(payload: { mode?: string; actors?: Array<Record<string, unknown>> }): void {
  const actors = (payload.actors || []).slice(0, MAX_AGENTS)
  setBadge(payload.mode || 'live')

  // Verified tool events only. A character shows activity solely when the
  // server observed a real, unmatched tool start for that run; nothing here is
  // inferred from recency. Keyed by renderer id so it survives re-polls.
  const activeToolByActor = toolState

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
    const activity = (actor as {
      run_activity?: { tool_active?: boolean; tool_id?: string; category?: string }
    }).run_activity
    const toolId = activity?.tool_active ? String(activity.tool_id || '') : ''
    const previous = activeToolByActor.get(id)

    if (toolId && toolId !== previous) {
      // A new verified tool action: close any previous one first, so the
      // renderer never holds two open tools for the same character.
      if (previous) {
        postToWebview({ type: 'agentToolDone', id, toolId: previous })
        postToWebview({ type: 'agentToolsClear', id })
      }
      activeToolByActor.set(id, toolId)
      postToWebview({ type: 'agentToolStart', id, toolId, status: String(activity?.category || 'other') })
      postToWebview({ type: 'agentStatus', id, status: 'active' })
    } else if (!toolId && previous) {
      // Cleared or expired: stop the animation rather than freeze it busy.
      activeToolByActor.delete(id)
      postToWebview({ type: 'agentToolDone', id, toolId: previous })
      postToWebview({ type: 'agentToolsClear', id })
      postToWebview({ type: 'agentStatus', id, status: 'idle' })
    } else if (!toolId) {
      // No verified event: neutral. Never claim work we cannot observe.
      postToWebview({ type: 'agentStatus', id, status: 'idle' })
    }
  }

  for (const [pid, id] of [...idByActor.entries()]) {
    if (!seen.has(pid)) {
      postToWebview({ type: 'agentClosed', id })
      activeToolByActor.delete(id)
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
    if (!res.ok) {
      // Reviewer P2: an outage after login must not keep showing a green LIVE badge.
      setDegraded(true)
      return
    }
    const data = (await res.json()) as { degraded?: boolean }
    setDegraded(data?.degraded === true)
    applyPayload(data as unknown as Parameters<typeof applyPayload>[0])
  } catch {
    // Reviewer P2: network failure is not health.
    setDegraded(true)
  }
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
}

export async function initHermesBridge(): Promise<void> {
  onWebviewMessage(async (msg) => {
    if (msg.type === 'webviewReady') {
      // React is mounted and listening now — load assets, then start feeding it.
      await handleReady()
      await poll()
      // Restore only AFTER the first payload: agents must exist before a layout
      // is loaded, otherwise restored agents get stuck in the spawn animation.
      restoreSavedLayout()
      window.setInterval(poll, POLL_MS)
      hideInertControls()
      hideInertSettings()
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
