/** Layout and fling physics for the champion pools (SPEC 17.4). Pure, so it can be tested. */

export const BUBBLE_PX = 56
export const CELL_PX = 68
export const POOL_PAD = 14

export type Point = { x: number; y: number }

/** Small deterministic hash so each champion's starting spot is stable between visits. */
export function hash(str: string): number {
  let h = 2166136261
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) / 4294967296
}

export function columns(width: number): number {
  return Math.max(1, Math.floor((width - POOL_PAD * 2) / CELL_PX))
}

export function poolHeight(count: number, width: number, minHeight = 200): number {
  const rows = Math.ceil(count / columns(width))
  return Math.max(minHeight, rows * CELL_PX + POOL_PAD * 2)
}

/**
 * Scatter champions over a loose grid in the given order (alphabetical keeps them findable),
 * nudged by a per-champion jitter so it looks like floating, not a spreadsheet.
 */
export function initialLayout(ids: string[], width: number): Map<string, Point> {
  const cols = columns(width)
  const spareX = width - POOL_PAD * 2 - cols * CELL_PX
  const out = new Map<string, Point>()
  ids.forEach((id, i) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    const jx = (hash(id) - 0.5) * (CELL_PX - BUBBLE_PX)
    const jy = (hash(id + '#') - 0.5) * (CELL_PX - BUBBLE_PX)
    out.set(id, {
      x: POOL_PAD + spareX / 2 + col * CELL_PX + (CELL_PX - BUBBLE_PX) / 2 + jx,
      y: POOL_PAD + row * CELL_PX + (CELL_PX - BUBBLE_PX) / 2 + jy,
    })
  })
  return out
}

export function clampToPool(p: Point, width: number, height: number): Point {
  return {
    x: Math.min(Math.max(p.x, 4), Math.max(4, width - BUBBLE_PX - 4)),
    y: Math.min(Math.max(p.y, 4), Math.max(4, height - BUBBLE_PX - 4)),
  }
}

export const FRICTION = 0.92 // per 16ms frame
const STOP_SPEED = 0.05 // px per ms

/** One physics step for a flung bubble: move, bounce off the pool walls, slow down. */
export function step(
  pos: Point,
  vel: Point, // px per ms
  dtMs: number,
  width: number,
  height: number,
): { pos: Point; vel: Point; moving: boolean } {
  let x = pos.x + vel.x * dtMs
  let y = pos.y + vel.y * dtMs
  let vx = vel.x
  let vy = vel.y
  const maxX = width - BUBBLE_PX - 4
  const maxY = height - BUBBLE_PX - 4
  if (x < 4) {
    x = 4
    vx = Math.abs(vx) * 0.7
  }
  if (x > maxX) {
    x = maxX
    vx = -Math.abs(vx) * 0.7
  }
  if (y < 4) {
    y = 4
    vy = Math.abs(vy) * 0.7
  }
  if (y > maxY) {
    y = maxY
    vy = -Math.abs(vy) * 0.7
  }
  const f = FRICTION ** (dtMs / 16)
  vx *= f
  vy *= f
  return { pos: { x, y }, vel: { x: vx, y: vy }, moving: Math.hypot(vx, vy) > STOP_SPEED }
}
