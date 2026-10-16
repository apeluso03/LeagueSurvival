import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api } from '../api/client'
import { registerTeamColors } from '../lib/teams'
import type { Champion, Player } from '../types'

export const useSettings = () => useQuery({ queryKey: ['settings'], queryFn: api.settings })
export const usePlayers = () => useQuery({ queryKey: ['players'], queryFn: api.players })
export const useRuns = () => useQuery({ queryKey: ['runs'], queryFn: api.runs })

/** Riot key and sync status. `check` makes the backend test the key with one Riot call. */
export const useRiotStatus = (check = false) =>
  useQuery({ queryKey: ['riot-status', check], queryFn: () => api.riotStatus(check) })

export const usePlayerStats = (runId: number | null, challengeOnly: boolean) =>
  useQuery({
    queryKey: ['stats', runId, challengeOnly],
    queryFn: () => api.playerStats({ run_id: runId ?? undefined, challenge_only: challengeOnly }),
  })

export const useChampions = () =>
  useQuery({ queryKey: ['champions'], queryFn: api.champions, staleTime: Infinity })

// While a game is pending, poll so results applied by the backend's matcher show up on their own.
const PENDING_REFRESH_MS = 15_000

export const useRun = (id: number | null | undefined) =>
  useQuery({
    queryKey: ['run', id],
    queryFn: () => api.run(id!),
    enabled: id != null,
    refetchInterval: (q) => (q.state.data?.pending_game_id ? PENDING_REFRESH_MS : false),
  })

export const usePool = (runId: number | null | undefined) =>
  useQuery({ queryKey: ['pool', runId], queryFn: () => api.pool(runId!), enabled: runId != null })

/** Short per-champion numbers for the Pool cards (one request for the whole run). */
export const useChampionLines = (runId: number | null | undefined) =>
  useQuery({ queryKey: ['champion-lines', runId], queryFn: () => api.championLines(runId!), enabled: runId != null })

/** Per player, per rolled champion: their record, Riot games and the group's record. */
export const useOptionFacts = (gameId: number | null | undefined) =>
  useQuery({ queryKey: ['option-facts', gameId], queryFn: () => api.optionFacts(gameId!), enabled: gameId != null })

export const useAchievements = () => useQuery({ queryKey: ['achievements'], queryFn: api.achievements })

/** Suggested roles, runes and items for the rolled champions (high-elo data). */
export const useComp = (championIds: string[], exclude: string[] = []) =>
  useQuery({
    queryKey: ['comp', ...championIds, '|', ...exclude],
    queryFn: () => api.comp(championIds, exclude),
    enabled: championIds.length > 0,
    staleTime: 5 * 60_000,
  })

export const usePoolEvents = (runId: number | null | undefined) =>
  useQuery({ queryKey: ['events', runId], queryFn: () => api.events(runId!), enabled: runId != null })

export const useGames = (runId: number | null | undefined) =>
  useQuery({ queryKey: ['games', runId], queryFn: () => api.games(runId!), enabled: runId != null })

export const useGame = (id: number | null | undefined) =>
  useQuery({
    queryKey: ['game', id],
    queryFn: () => api.game(id!),
    enabled: id != null,
    refetchInterval: (q) => (q.state.data?.status === 'pending' ? PENDING_REFRESH_MS : false),
  })

export const useShop = (runId: number | null | undefined) =>
  useQuery({ queryKey: ['shop', runId], queryFn: () => api.shop(runId!), enabled: runId != null })

/** Gold and item status for every player in the run. */
export const useEconomy = (runId: number | null | undefined) =>
  useQuery({ queryKey: ['economy', runId], queryFn: () => api.economy(runId!), enabled: runId != null })

export const useGold = (runId: number | null | undefined, playerId: number | null | undefined) =>
  useQuery({
    queryKey: ['gold', runId, playerId],
    queryFn: () => api.gold(runId!, playerId!),
    enabled: runId != null && playerId != null,
  })

export const useInventory = (runId: number | null | undefined, playerId: number | null | undefined) =>
  useQuery({
    queryKey: ['inventory', runId, playerId],
    queryFn: () => api.inventory(runId!, playerId!),
    enabled: runId != null && playerId != null,
  })

export const useTokens = (runId: number | null | undefined) =>
  useQuery({
    queryKey: ['tokens', runId],
    queryFn: () => api.tokens({ run_id: runId!, unused_only: true }),
    enabled: runId != null,
  })

/**
 * The live game for the pending challenge game. Checks every 3s while live stats are coming in,
 * every 10s while a game is pending (to notice it starting), and every 30s otherwise.
 */
export const useLive = () =>
  useQuery({
    queryKey: ['live'],
    queryFn: api.live,
    refetchInterval: (q) => (q.state.data?.live?.streaming ? 3_000 : q.state.data?.game_id ? 10_000 : 30_000),
  })

/** The active run, resolved through settings. */
export function useActiveRun() {
  const settings = useSettings()
  const run = useRun(settings.data?.active_run_id)
  return { settings, run, runId: settings.data?.active_run_id ?? null }
}

export function useChampionMap() {
  const { data } = useChampions()
  return useMemo(() => new Map<string, Champion>((data ?? []).map((c) => [c.id, c])), [data])
}

/** Keeps team colours in sync with the players' chosen colours (call near the top of the page). */
export function useTeamColors() {
  const { data } = usePlayers()
  registerTeamColors(data)
}

export function usePlayerMap() {
  const { data } = usePlayers()
  return useMemo(() => new Map<number, Player>((data ?? []).map((p) => [p.id, p])), [data])
}

/** A mutation that refreshes all game state (everything but the champion list) when it succeeds. */
export function useAction<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    // Not awaited on purpose: the refetch can unmount the caller (e.g. the pending game panel), and
    // per-call onSuccess callbacks are skipped once that happens.
    onSuccess: () => {
      void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'champions' && q.queryKey[0] !== 'me' })
    },
  })
}
