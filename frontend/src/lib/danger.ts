/**
 * How close the run is to running out of champions (Wheels danger meter).
 * A spin gives everyone their full options while alive >= players x options; below that the
 * options shrink evenly, and a spin is blocked once there are fewer champions than players.
 * Each loss eliminates at most one champion per player.
 */
export interface Danger {
  full: number // champions needed for full options
  minimum: number // champions needed to spin at all
  lossesUntilShrink: number // losses that still leave full options
  lossesUntilBlocked: number // losses that still leave a spin possible
  level: 'safe' | 'warning' | 'danger'
}

export function dangerInfo(alive: number, players: number, options: number): Danger {
  const p = Math.max(1, players)
  const full = p * options
  const lossesUntilShrink = alive >= full ? Math.floor((alive - full) / p) : -1
  const lossesUntilBlocked = alive >= p ? Math.floor((alive - p) / p) : -1
  const level = alive < full || lossesUntilShrink < 3 ? 'danger' : lossesUntilShrink < 10 ? 'warning' : 'safe'
  return { full, minimum: p, lossesUntilShrink, lossesUntilBlocked, level }
}
