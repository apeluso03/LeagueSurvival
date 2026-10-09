/** Math for the case-opening reels (SPEC 17.3). Pure functions so they can be unit tested. */

export const CARD_PX = 108
export const GAP_PX = 6
export const STRIDE_PX = CARD_PX + GAP_PX
export const STRIP_LENGTH = 50
export const FINAL_INDEX = 43 // cards after the winner keep the strip full when it stops
export const SPIN_MS = 6500

/** Long, suspenseful slow-down: fast start, very gradual stop. */
export function easeOutQuart(t: number): number {
  const c = Math.min(Math.max(t, 0), 1)
  return 1 - (1 - c) ** 4
}

/**
 * Position (in strip pixels) under the center marker at progress t (0..1).
 * Starts with card 0 centered and ends inside the final card, `offset` px from its center.
 */
export function reelPosition(t: number, offset: number, finalIndex = FINAL_INDEX): number {
  const start = CARD_PX / 2
  const end = finalIndex * STRIDE_PX + CARD_PX / 2 + offset
  return start + (end - start) * easeOutQuart(t)
}

/** Which card is under the marker at a given strip position. */
export function cardIndexAt(position: number): number {
  return Math.floor(position / STRIDE_PX)
}

/** A random landing spot inside the winning card, never right at the edges. */
export function randomLandingOffset(rng: () => number = Math.random): number {
  return (rng() - 0.5) * CARD_PX * 0.76
}

/** Strip of champion ids with `finalId` at FINAL_INDEX; neighbors never repeat back to back. */
export function buildStrip(
  pool: string[],
  finalId: string,
  length = STRIP_LENGTH,
  finalIndex = FINAL_INDEX,
  rng: () => number = Math.random,
): string[] {
  const fillers = pool.length > 1 ? pool : [finalId]
  const strip: string[] = []
  for (let i = 0; i < length; i++) {
    if (i === finalIndex) {
      strip.push(finalId)
      continue
    }
    let pick = fillers[Math.floor(rng() * fillers.length)]
    for (let tries = 0; fillers.length > 2 && tries < 10; tries++) {
      const clashes = pick === strip[i - 1] || (i === finalIndex - 1 && pick === finalId) || (i === finalIndex + 1 && pick === finalId)
      if (!clashes) break
      pick = fillers[Math.floor(rng() * fillers.length)]
    }
    strip.push(pick)
  }
  return strip
}

/** Card accent color by the champion's main class, like item rarity in a case opening. */
export const CLASS_COLORS: Record<string, string> = {
  Assassin: '#e0434f',
  Mage: '#8b5cf6',
  Fighter: '#e8823a',
  Tank: '#4fae6b',
  Marksman: '#e3c04d',
  Support: '#0ac8b9',
}

export const classColor = (tags: string[] | undefined) => CLASS_COLORS[tags?.[0] ?? ''] ?? '#5b5a56'

/**
 * The reel's slow-down as a CSS `linear()` easing, so the browser's compositor can run the whole
 * spin without JavaScript touching every frame. Sampled densely enough to match easeOutQuart.
 */
export function quartEasing(points = 48): string {
  const stops: string[] = []
  for (let i = 0; i <= points; i++) {
    const t = i / points
    stops.push(`${easeOutQuart(t).toFixed(4)} ${(t * 100).toFixed(2)}%`)
  }
  return `linear(${stops.join(', ')})`
}

/** Older browsers without `linear()` get the closest standard curve. */
export const QUART_FALLBACK = 'cubic-bezier(0.165, 0.84, 0.44, 1)'

/** Inverse of easeOutQuart: the progress t at which the eased value reaches p. */
export function inverseQuart(p: number): number {
  const c = Math.min(Math.max(p, 0), 1)
  return 1 - (1 - c) ** 0.25
}

/**
 * When (ms after the spin starts) each card crosses the marker, so tick sounds can be scheduled
 * up front instead of watched frame by frame. Returns [ms, progress] pairs.
 */
export function tickSchedule(offset: number, durationMs: number, finalIndex = FINAL_INDEX): [number, number][] {
  const start = reelPosition(0, offset, finalIndex)
  const end = reelPosition(1, offset, finalIndex)
  const out: [number, number][] = []
  for (let k = 1; k * STRIDE_PX <= end; k++) {
    const t = inverseQuart((k * STRIDE_PX - start) / (end - start))
    if (t > 0 && t < 1) out.push([t * durationMs, t])
  }
  return out
}
