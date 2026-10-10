/**
 * Browser-side asset loader.
 * Loads PNG assets directly via Canvas API and converts to SpriteData format
 * (2D arrays of hex color strings), matching the VSCode extension's pngjs-based loader.
 */

const PNG_ALPHA_THRESHOLD = 128
const WALL_PIECE_WIDTH = 16
const WALL_PIECE_HEIGHT = 32
const WALL_GRID_COLS = 4
const WALL_BITMASK_COUNT = 16
const FLOOR_PATTERN_COUNT = 7
const FLOOR_TILE_SIZE = 16
const CHAR_FRAME_W = 16
const CHAR_FRAME_H = 32
const CHAR_FRAMES_PER_ROW = 7
const CHAR_COUNT = 6

interface CharacterDirectionSprites {
  down: string[][][]
  up: string[][][]
  right: string[][][]
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`Failed to load image: ${url}`))
    img.src = url
  })
}

function getImageData(img: HTMLImageElement): ImageData {
  const canvas = document.createElement('canvas')
  canvas.width = img.width
  canvas.height = img.height
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(img, 0, 0)
  return ctx.getImageData(0, 0, img.width, img.height)
}

function pixelToHex(data: Uint8ClampedArray, idx: number): string {
  const r = data[idx]
  const g = data[idx + 1]
  const b = data[idx + 2]
  const a = data[idx + 3]
  if (a < PNG_ALPHA_THRESHOLD) return ''
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`.toUpperCase()
}

export async function loadCharacterSprites(): Promise<CharacterDirectionSprites[]> {
  const characters: CharacterDirectionSprites[] = []
  const directions = ['down', 'up', 'right'] as const

  for (let ci = 0; ci < CHAR_COUNT; ci++) {
    const img = await loadImage(`${import.meta.env.BASE_URL}assets/characters/char_${ci}.png`)
    const imageData = getImageData(img)
    const { data, width } = imageData

    const charData: CharacterDirectionSprites = { down: [], up: [], right: [] }

    for (let dirIdx = 0; dirIdx < directions.length; dirIdx++) {
      const dir = directions[dirIdx]
      const rowOffsetY = dirIdx * CHAR_FRAME_H
      const frames: string[][][] = []

      for (let f = 0; f < CHAR_FRAMES_PER_ROW; f++) {
        const sprite: string[][] = []
        const frameOffsetX = f * CHAR_FRAME_W
        for (let y = 0; y < CHAR_FRAME_H; y++) {
          const row: string[] = []
          for (let x = 0; x < CHAR_FRAME_W; x++) {
            const idx = ((rowOffsetY + y) * width + (frameOffsetX + x)) * 4
            row.push(pixelToHex(data, idx))
          }
          sprite.push(row)
        }
        frames.push(sprite)
      }
      charData[dir] = frames
    }
    characters.push(charData)
  }

  return characters
}

export async function loadWallSprites(): Promise<string[][][]> {
  try {
    const img = await loadImage(`${import.meta.env.BASE_URL}assets/walls.png`)
    const imageData = getImageData(img)
    const { data, width } = imageData

    const sprites: string[][][] = []
    for (let mask = 0; mask < WALL_BITMASK_COUNT; mask++) {
      const ox = (mask % WALL_GRID_COLS) * WALL_PIECE_WIDTH
      const oy = Math.floor(mask / WALL_GRID_COLS) * WALL_PIECE_HEIGHT
      const sprite: string[][] = []
      for (let r = 0; r < WALL_PIECE_HEIGHT; r++) {
        const row: string[] = []
        for (let c = 0; c < WALL_PIECE_WIDTH; c++) {
          const idx = ((oy + r) * width + (ox + c)) * 4
          row.push(pixelToHex(data, idx))
        }
        sprite.push(row)
      }
      sprites.push(sprite)
    }
    return sprites
  } catch {
    console.warn('[AssetLoader] No walls.png found, using fallback')
    return []
  }
}

export async function loadFloorSprites(): Promise<string[][][]> {
  try {
    const img = await loadImage(`${import.meta.env.BASE_URL}assets/floors.png`)
    const imageData = getImageData(img)
    const { data, width } = imageData

    const sprites: string[][][] = []
    for (let t = 0; t < FLOOR_PATTERN_COUNT; t++) {
      const sprite: string[][] = []
      for (let y = 0; y < FLOOR_TILE_SIZE; y++) {
        const row: string[] = []
        for (let x = 0; x < FLOOR_TILE_SIZE; x++) {
          const px = t * FLOOR_TILE_SIZE + x
          const idx = (y * width + px) * 4
          row.push(pixelToHex(data, idx))
        }
        sprite.push(row)
      }
      sprites.push(sprite)
    }
    return sprites
  } catch {
    console.warn('[AssetLoader] No floors.png found, using fallback')
    return []
  }
}

export interface FurnitureAsset {
  id: string
  name: string
  label: string
  category: string
  file: string
  width: number
  height: number
  footprintW: number
  footprintH: number
  isDesk: boolean
  canPlaceOnWalls: boolean
  partOfGroup?: boolean
  groupId?: string
  canPlaceOnSurfaces?: boolean
  backgroundTiles?: number
  orientation?: string
  state?: string
}

interface FurnitureCatalogData {
  assets: FurnitureAsset[]
}

export async function loadFurnitureAssets(): Promise<{
  catalog: FurnitureAsset[]
  sprites: Record<string, string[][]>
} | null> {
  try {
    const resp = await fetch(`${import.meta.env.BASE_URL}assets/furniture/furniture-catalog.json`)
    if (!resp.ok) return null
    const catalogData = (await resp.json()) as FurnitureCatalogData
    const catalog = catalogData.assets || []
    const sprites: Record<string, string[][]> = {}

    for (const asset of catalog) {
      try {
        let filePath = asset.file
        if (!filePath.startsWith('assets/')) {
          filePath = `assets/${filePath}`
        }
        const img = await loadImage(`${import.meta.env.BASE_URL}${filePath}`)
        const imageData = getImageData(img)
        const { data, width } = imageData

        const sprite: string[][] = []
        for (let y = 0; y < asset.height; y++) {
          const row: string[] = []
          for (let x = 0; x < asset.width; x++) {
            const idx = (y * width + x) * 4
            row.push(pixelToHex(data, idx))
          }
          sprite.push(row)
        }
        sprites[asset.id] = sprite
      } catch {
        // Skip missing assets
      }
    }

    return { catalog, sprites }
  } catch {
    console.log('[AssetLoader] No furniture catalog found')
    return null
  }
}

export async function loadDefaultLayout(): Promise<Record<string, unknown> | null> {
  try {
    const resp = await fetch(`${import.meta.env.BASE_URL}assets/default-layout.json`)
    if (!resp.ok) return null
    return await resp.json()
  } catch {
    return null
  }
}
