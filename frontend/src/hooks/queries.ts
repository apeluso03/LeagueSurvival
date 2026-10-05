import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api } from '../api/client'
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

export const useGames = (runId: number | null | undefined) =>
  useQuery({ queryKey: ['games', runId], queryFn: () => api.games(runId!), enabled: runId != null })

export const useGame = (id: number | null | undefined) =>
  useQuery({
    queryKey: ['game', id],
    queryFn: () => api.game(id!),
    enabled: id != null,
    refetchInterval: (q) => (q.state.data?.status === 'pending' ? PENDING_REFRESH_MS : false),
  })

export const useTokens = (runId: number | null | undefined) =>
  useQuery({
    queryKey: ['tokens', runId],
    queryFn: () => api.tokens({ run_id: runId!, unused_only: true }),
    enabled: runId != null,
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
      void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'champions' })
    },
  })
}
