import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { api } from '../api/client'
import type { Me, Run } from '../types'
import { useActiveRun } from './queries'

/** Who's signed in (or that the site still needs setting up). */
export const useMe = () => useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60_000 })

/**
 * What the signed-in user may do in the group they're viewing. Mirrors the backend
 * (routers/access.py), which is what actually enforces it; this only decides which buttons to show.
 *
 * - The group's owner manages everything in the group.
 * - A run's owner runs spins, results and settings for it, and handles every player's shop in it.
 * - Everyone else handles their own player's gold, shop, items and revive tokens.
 * - The site admin only gets the site-wide controls (`isSiteAdmin`).
 */
export function useAccess(forRun?: Run | null) {
  const data = useMe().data
  const me = data?.user ?? null
  const group = data?.group ?? null
  const { run: active } = useActiveRun()
  const run = forRun === undefined ? active.data : forRun
  const isOwner = group?.role === 'owner'
  const myPlayerId = group?.player_id ?? null

  const manages = useCallback(
    (r: Run | null | undefined) => !!me && (isOwner || (!!r && r.owner_user_id === me.id)),
    [me, isOwner],
  )
  const canManage = manages(run)
  const canActFor = useCallback(
    (playerId: number | null | undefined) => canManage || (myPlayerId != null && myPlayerId === playerId),
    [canManage, myPlayerId],
  )
  return {
    user: me,
    group,
    groups: data?.groups ?? [],
    /** The owner of the group being viewed. */
    isOwner,
    /** Site-wide controls: site invites, open sign-up, build crawler, Riot data deletion. */
    isSiteAdmin: !!me?.is_admin,
    myPlayerId,
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
    onSettled: () => signedIn({ user: null, groups: [], group: null, setup_needed: false, players: [], open_signup: false }),
  })
  return { signedIn, logout }
}
