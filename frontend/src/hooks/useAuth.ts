import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { api } from '../api/client'
import type { Me, Run } from '../types'
import { useActiveRun } from './queries'

/** Who's signed in (or that the site still needs setting up). */
export const useMe = () => useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60_000 })

/**
 * What the signed-in user may do. Mirrors the backend (routers/access.py), which is what actually
 * enforces it; this only decides which buttons to show.
 *
 * - The site owner (`is_admin`) manages everything.
 * - A run's owner runs spins, results and settings for it, and handles every player's shop in it.
 * - Everyone else handles their own player's gold, shop, items and revive tokens.
 */
export function useAccess(forRun?: Run | null) {
  const me = useMe().data?.user ?? null
  const { run: active } = useActiveRun()
  const run = forRun === undefined ? active.data : forRun

  const manages = useCallback(
    (r: Run | null | undefined) => !!me && (me.is_admin || (!!r && r.owner_user_id === me.id)),
    [me],
  )
  const canManage = manages(run)
  const canActFor = useCallback(
    (playerId: number | null | undefined) => canManage || (me?.player_id != null && me.player_id === playerId),
    [canManage, me],
  )
  return {
    user: me,
    isAdmin: !!me?.is_admin,
    myPlayerId: me?.player_id ?? null,
    /** Spins, results, undo, pool fixes and shop settings for the run. */
    canManage,
    manages,
    /** Buy and use items, see gold, spend revive tokens for this player. */
    canActFor,
  }
}

/** After signing in, out or up: forget the last person's data and start fresh. */
export function useSession() {
  const qc = useQueryClient()
  const signedIn = useCallback(
    (me: Me) => {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'champions' })
      qc.setQueryData(['me'], me)
    },
    [qc],
  )
  const logout = useMutation({
    mutationFn: api.logout,
    onSettled: () => signedIn({ user: null, setup_needed: false, players: [] }),
  })
  return { signedIn, logout }
}
