import type { Assignment, LiveGame, PlayerRole, Role } from '../types'

/**
 * Each player's real role, when it's known: set by hand on the spin first, then what the live game
 * shows (their lane in the game client, or Smite for jungle). Everyone else gets a suggested role.
 */
export function realRoles(
  assignments: Assignment[] | undefined,
  live: LiveGame | null | undefined,
): Map<number, PlayerRole> {
  const out = new Map<number, PlayerRole>()
  for (const [pid, r] of Object.entries(live?.roles ?? {})) {
    // Hand-set roles come from the assignments when we have them (fresher after a change).
    if (r.source !== 'set' || !assignments) out.set(Number(pid), r)
  }
  for (const a of assignments ?? []) {
    if (a.played_role) out.set(a.player_id, { role: a.played_role, source: 'set' })
  }
  return out
}

/** For the build suggester: champion id -> role, for the players whose real role is known. */
export function rolesByChampion(
  players: { playerId: number; championId: string }[],
  roles: Map<number, PlayerRole>,
): Record<string, Role> {
  const out: Record<string, Role> = {}
  for (const p of players) {
    const r = roles.get(p.playerId)
    if (r) out[p.championId] = r.role
  }
  return out
}
