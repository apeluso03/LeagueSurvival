/**
 * Team colour per player, like a broadcast's team colours. Players can pick their own in Settings;
 * otherwise it comes from their id, so the first eight players never share one.
 */
export const TEAM_COLORS = ['#2e9bff', '#ff4655', '#f0b232', '#a970ff', '#2fd27a', '#ff8a1f', '#19d3e6', '#ff5fb4']

export const defaultTeamColor = (playerId: number) =>
  TEAM_COLORS[(((playerId - 1) % TEAM_COLORS.length) + TEAM_COLORS.length) % TEAM_COLORS.length]

// Chosen colours, kept in sync with the players list by the layout (see registerTeamColors).
let chosen = new Map<number, string>()

export function registerTeamColors(players: { id: number; color: string | null }[] | undefined) {
  chosen = new Map((players ?? []).filter((p) => p.color).map((p) => [p.id, p.color!]))
}

export const teamColor = (playerId: number) => chosen.get(playerId) ?? defaultTeamColor(playerId)
