import type { LivePlayer, TeamId } from '../types'

export const BLUE: TeamId = 100
export const RED: TeamId = 200
// The two sides' colours (blue a step darker than the accent so both read on the dark surface).
export const SIDE_COLOR: Record<TeamId, string> = { 100: '#1f8ae6', 200: '#e5283c' }
export const SIDE_NAME: Record<TeamId, string> = { 100: 'Blue', 200: 'Red' }

export const LANES = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY'] as const
export const LANE_SHORT: Record<string, string> = { TOP: 'TOP', JUNGLE: 'JG', MIDDLE: 'MID', BOTTOM: 'BOT', UTILITY: 'SUP' }

export const DRAGON_COLOR: Record<string, string> = {
  Fire: '#e8642c',
  Water: '#3fb6c8',
  Earth: '#a0703c',
  Air: '#c9d6e3',
  Hextech: '#4bc6e8',
  Chemtech: '#8bc34a',
  Elder: '#e8e1c4',
}

/** Game clock: 754 -> "12:34". */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** 12400 -> "12.4K", 950 -> "950", with an optional sign. */
export function goldShort(n: number, signed = false): string {
  const sign = signed ? (n > 0 ? '+' : n < 0 ? '−' : '') : n < 0 ? '−' : ''
  const a = Math.abs(n)
  const body = a >= 1000 ? `${(a / 1000).toFixed(a >= 10000 ? 0 : 1)}K` : String(Math.round(a))
  return `${sign}${body}`
}

export interface LaneRow {
  lane: string // "TOP" ... or "" when positions are unknown
  blue: LivePlayer | undefined
  red: LivePlayer | undefined
}

/**
 * Pair the two teams lane by lane, like a broadcast's player list. Uses the game's positions when
 * they're there (matchmade games); anyone left over is paired in the order they were listed.
 */
export function pairLanes(players: LivePlayer[]): LaneRow[] {
  const byTeam = (team: TeamId) => players.filter((p) => p.team === team)
  const blue = byTeam(BLUE)
  const red = byTeam(RED)
  const rows: LaneRow[] = []
  const usedB = new Set<LivePlayer>()
  const usedR = new Set<LivePlayer>()
  for (const lane of LANES) {
    const b = blue.find((p) => p.position === lane && !usedB.has(p))
    const r = red.find((p) => p.position === lane && !usedR.has(p))
    if (!b && !r) continue
    if (b) usedB.add(b)
    if (r) usedR.add(r)
    rows.push({ lane, blue: b, red: r })
  }
  const restB = blue.filter((p) => !usedB.has(p))
  const restR = red.filter((p) => !usedR.has(p))
  for (let i = 0; i < Math.max(restB.length, restR.length); i++) rows.push({ lane: '', blue: restB[i], red: restR[i] })
  return rows
}

/** Live progress toward a contract goal, when the goal can be seen during the game. */
export function contractProgress(goal: string, target: string, p: LivePlayer | undefined): { now: number; target: number } | null {
  if (!p) return null
  const t = Number(target)
  if (!Number.isFinite(t)) return null
  if (goal === 'kills') return { now: p.kills, target: t }
  if (goal === 'assists') return { now: p.assists, target: t }
  return null
}
