/**
 * Standalone Bridge - Replaces the VSCode extension backend.
 * Loads assets directly in the browser and manages agent state.
 */

import { postToWebview, onWebviewMessage } from './vscodeApi.js'
import {
  loadCharacterSprites,
  loadWallSprites,
  loadFloorSprites,
  loadFurnitureAssets,
  loadDefaultLayout,
} from './browserAssetLoader.js'

const LAYOUT_STORAGE_KEY = 'pixel-agents-layout'
const SEATS_STORAGE_KEY = 'pixel-agents-seats'
const SOUND_STORAGE_KEY = 'pixel-agents-sound'

/** Whether dynamic furniture assets (catalog + sprites) loaded successfully */
let furnitureAssetsLoaded = false

/** Hardcoded furniture types that work without the dynamic catalog */
const BUILTIN_FURNITURE_TYPES = new Set(['desk', 'bookshelf', 'plant', 'cooler', 'whiteboard', 'chair', 'pc', 'lamp'])

/** Check if a layout contains furniture types that require the dynamic catalog */
function layoutNeedsCatalog(layout: Record<string, unknown>): boolean {
  const furniture = layout.furniture as Array<{ type: string }> | undefined
  if (!furniture || furniture.length === 0) return false
  return furniture.some((f) => !BUILTIN_FURNITURE_TYPES.has(f.type))
}

function saveLayout(layout: Record<string, unknown>): void {
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout))
  } catch { /* quota exceeded or unavailable */ }
}

function loadSavedLayout(): Record<string, unknown> | null {
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return null
}

export async function initStandaloneBridge(): Promise<void> {
  // Handle messages from the webview (React app)
  onWebviewMessage(async (msg) => {
    if (msg.type === 'webviewReady') {
      await handleWebviewReady()
    } else if (msg.type === 'saveLayout') {
      saveLayout(msg.layout as Record<string, unknown>)
    } else if (msg.type === 'saveAgentSeats') {
      try {
        localStorage.setItem(SEATS_STORAGE_KEY, JSON.stringify(msg.seats))
      } catch { /* ignore */ }
    } else if (msg.type === 'setSoundEnabled') {
      try {
        localStorage.setItem(SOUND_STORAGE_KEY, JSON.stringify(msg.enabled))
      } catch { /* ignore */ }
    } else if (msg.type === 'openClaude') {
      // In standalone mode, we create a demo agent
      createDemoAgent()
    } else if (msg.type === 'focusAgent') {
      postToWebview({ type: 'agentSelected', id: msg.id })
    } else if (msg.type === 'closeAgent') {
      removeDemoAgent(msg.id as number)
    } else if (msg.type === 'exportLayout') {
      const layout = loadSavedLayout()
      if (layout) {
        const blob = new Blob([JSON.stringify(layout, null, 2)], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'pixel-agents-layout.json'
        a.click()
        URL.revokeObjectURL(url)
      }
    } else if (msg.type === 'importLayout') {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.json'
      input.onchange = async () => {
        const file = input.files?.[0]
        if (!file) return
        try {
          const text = await file.text()
          const imported = JSON.parse(text) as Record<string, unknown>
          if (imported.version !== 1 || !Array.isArray(imported.tiles)) return
          // Reject layouts with ASSET_* furniture when catalog is not available
          if (!furnitureAssetsLoaded && layoutNeedsCatalog(imported)) {
            console.warn('[Bridge] Imported layout requires furniture catalog that is not loaded — skipping')
            return
          }
          saveLayout(imported)
          postToWebview({ type: 'layoutLoaded', layout: imported })
        } catch { /* invalid file */ }
      }
      input.click()
    }
  })
}

async function handleWebviewReady(): Promise<void> {
  // Load sound settings
  try {
    const soundRaw = localStorage.getItem(SOUND_STORAGE_KEY)
    const soundEnabled = soundRaw ? JSON.parse(soundRaw) : true
    postToWebview({ type: 'settingsLoaded', soundEnabled })
  } catch { /* ignore */ }

  // Load character sprites
  try {
    const characters = await loadCharacterSprites()
    postToWebview({ type: 'characterSpritesLoaded', characters })
  } catch (err) {
    console.error('[Bridge] Failed to load character sprites:', err)
  }

  // Load floor tiles
  try {
    const floorSprites = await loadFloorSprites()
    if (floorSprites.length > 0) {
      postToWebview({ type: 'floorTilesLoaded', sprites: floorSprites })
    }
  } catch { /* ignore */ }

  // Load wall tiles
  try {
    const wallSprites = await loadWallSprites()
    if (wallSprites.length > 0) {
      postToWebview({ type: 'wallTilesLoaded', sprites: wallSprites })
    }
  } catch { /* ignore */ }

  // Load furniture assets
  try {
    const assets = await loadFurnitureAssets()
    if (assets) {
      furnitureAssetsLoaded = true
      postToWebview({
        type: 'furnitureAssetsLoaded',
        catalog: assets.catalog,
        sprites: assets.sprites,
      })
    }
  } catch { /* ignore */ }

  // Send existing agents (restore from session)
  const agentMeta = loadAgentMeta()
  const agentIds = Object.keys(agents).map(Number)
  if (agentIds.length > 0) {
    postToWebview({
      type: 'existingAgents',
      agents: agentIds,
      agentMeta,
      folderNames: {},
    })
  }

  // Load layout (saved or default)
  // The default-layout.json uses ASSET_* furniture IDs that require the dynamic
  // furniture catalog. If the catalog didn't load, skip it and let the app fall
  // back to the hardcoded createDefaultLayout() which has embedded sprites.
  const savedLayout = loadSavedLayout()
  if (savedLayout && furnitureAssetsLoaded) {
    postToWebview({ type: 'layoutLoaded', layout: savedLayout })
  } else if (furnitureAssetsLoaded) {
    const defaultLayout = await loadDefaultLayout()
    if (defaultLayout) {
      postToWebview({ type: 'layoutLoaded', layout: defaultLayout })
    } else {
      postToWebview({ type: 'layoutLoaded', layout: null })
    }
  } else {
    // No furniture catalog — use hardcoded default layout with built-in sprites.
    // Clear stale saved layout that references ASSET_* types to prevent it from
    // accumulating in localStorage and being accidentally exported.
    if (savedLayout && layoutNeedsCatalog(savedLayout)) {
      try { localStorage.removeItem(LAYOUT_STORAGE_KEY) } catch { /* ignore */ }
      try { localStorage.removeItem(SEATS_STORAGE_KEY) } catch { /* ignore */ }
      console.log('[Bridge] Cleared stale layout from localStorage (requires missing furniture catalog)')
    }
    postToWebview({ type: 'layoutLoaded', layout: null })
  }

  // Auto-spawn demo agents if none exist so the scene isn't empty
  if (Object.keys(agents).length === 0) {
    const INITIAL_AGENT_COUNT = 3
    for (let i = 0; i < INITIAL_AGENT_COUNT; i++) {
      createDemoAgent()
    }
  }
}

// ── Demo Agent Management ────────────────────────────────────

let nextAgentId = 1
const agents: Record<number, { id: number; simulationTimer?: ReturnType<typeof setInterval> }> = {}

function loadAgentMeta(): Record<string, unknown> {
  try {
    const raw = localStorage.getItem(SEATS_STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return {}
}

// Tool names that agents can "use" in demo mode
const DEMO_TOOLS = [
  'Read', 'Edit', 'Write', 'Bash', 'Grep', 'Glob',
  'Agent', 'WebFetch', 'TodoWrite',
]

function createDemoAgent(): void {
  const id = nextAgentId++
  agents[id] = { id }
  postToWebview({ type: 'agentCreated', id })

  // Start simulating activity
  startAgentSimulation(id)
}

function removeDemoAgent(id: number): void {
  const agent = agents[id]
  if (!agent) return
  if (agent.simulationTimer) {
    clearInterval(agent.simulationTimer)
  }
  delete agents[id]
  postToWebview({ type: 'agentClosed', id })
}

function startAgentSimulation(id: number): void {
  const agent = agents[id]
  if (!agent) return

  let toolCounter = 0

  // Simulate agent activity with random tool usage
  const simulate = () => {
    if (!agents[id]) return

    const rand = Math.random()

    if (rand < 0.3) {
      // Start a tool
      const toolId = `tool_${id}_${toolCounter++}`
      const toolName = DEMO_TOOLS[Math.floor(Math.random() * DEMO_TOOLS.length)]
      postToWebview({
        type: 'agentToolStart',
        id,
        toolId,
        status: `${toolName}(...)`,
      })

      // Complete the tool after a delay
      setTimeout(() => {
        if (!agents[id]) return
        postToWebview({ type: 'agentToolDone', id, toolId })

        // Sometimes clear all tools (turn complete)
        if (Math.random() < 0.3) {
          postToWebview({ type: 'agentToolsClear', id })
        }
      }, 1000 + Math.random() * 3000)
    } else if (rand < 0.4) {
      // Agent waiting for input
      postToWebview({ type: 'agentStatus', id, status: 'waiting' })
      setTimeout(() => {
        if (!agents[id]) return
        postToWebview({ type: 'agentStatus', id, status: 'active' })
      }, 3000 + Math.random() * 5000)
    } else if (rand < 0.45) {
      // Permission needed
      postToWebview({ type: 'agentToolPermission', id })
      setTimeout(() => {
        if (!agents[id]) return
        postToWebview({ type: 'agentToolPermissionClear', id })
      }, 2000 + Math.random() * 4000)
    }
  }

  // Run simulation at random intervals
  agent.simulationTimer = setInterval(simulate, 2000 + Math.random() * 3000)

  // Initial activity after a brief delay
  setTimeout(simulate, 500)
}

export function getDemoAgentCount(): number {
  return Object.keys(agents).length
}
