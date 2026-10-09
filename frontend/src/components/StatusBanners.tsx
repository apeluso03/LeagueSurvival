import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api, isUnreachable } from '../api/client'
import { useActiveRun, useChampions } from '../hooks/queries'
import type { Game } from '../types'

/** Shown on every page when the backend isn't answering. Retries on its own. */
export function BackendDownBanner() {
  const { settings } = useActiveRun()
  // While queries retry, the latest failure is in failureReason (error is only set once retries stop).
  if (!isUnreachable(settings.error ?? settings.failureReason)) return null
  return (
    <div role="alert" className="border-b border-red-900 bg-red-950/80 px-4 py-2 text-sm text-red-100">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-1">
        <b>Can't reach the server.</b>
        <span>
          Start the app with <code>.\dev.ps1</code>. This page will reconnect by itself.
        </span>
        <button className="ml-auto underline" onClick={() => settings.refetch()}>
          Retry now
        </button>
      </div>
    </div>
  )
}

/** Shown when the champion list is empty, e.g. Data Dragon couldn't be reached on first start. */
export function NoChampionsBanner() {
  const champions = useChampions()
  const qc = useQueryClient()
  const refresh = useMutation({
    mutationFn: api.refreshChampions,
    onSuccess: () => qc.invalidateQueries(),
  })
  if (!champions.isSuccess || champions.data.length > 0) return null
  return (
    <div role="alert" className="border-b border-amber-900 bg-amber-950/70 px-4 py-2 text-sm text-amber-100">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-1">
        <b>The champion list didn't load.</b>
        <span>Check your internet connection and try again.</span>
        <button className="ml-auto underline" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
          {refresh.isPending ? 'Loading...' : 'Try again'}
        </button>
        {refresh.error && <span className="w-full text-red-200">{refresh.error.message}</span>}
      </div>
    </div>
  )
}

const RESULT_TEXT: Record<Game['status'], string> = { won: 'Win', lost: 'Loss', void: 'Voided', pending: '' }

/**
 * Pops up when the pending game gets a result while you're on another tab
 * (normally the Riot auto-matcher). The Wheels tab shows the result itself.
 */
export function BackgroundResultToast() {
  const { run } = useActiveRun()
  const location = useLocation()
  const pendingId = run.data?.pending_game_id ?? null
  const prev = useRef(pendingId)
  const [game, setGame] = useState<Game | null>(null)

  useEffect(() => {
    const before = prev.current
    prev.current = pendingId
    if (before != null && pendingId == null && location.pathname !== '/wheels') {
      api.game(before).then((g) => g.status !== 'pending' && setGame(g)).catch(() => {})
    }
  }, [pendingId, location.pathname])

  useEffect(() => {
    if (!game) return
    const t = setTimeout(() => setGame(null), 12_000)
    return () => clearTimeout(t)
  }, [game])

  if (!game) return null
  const tone = game.status === 'won' ? 'ring-emerald-500/60' : game.status === 'lost' ? 'ring-red-500/60' : 'ring-slate-500'
  return (
    <div
      role="status"
      className={`fixed right-4 bottom-4 left-4 z-50 mx-auto flex max-w-sm items-center gap-3 rounded-xl bg-slate-900 p-4 shadow-2xl ring-2 sm:left-auto ${tone}`}
    >
      <div className="flex-1 text-sm">
        <div className="font-semibold">
          Game #{game.id}: {RESULT_TEXT[game.status]}
          {game.result_source === 'auto' && <span className="text-sky-300"> (from Riot)</span>}
        </div>
        {game.eliminated.length > 0 && (
          <div className="text-slate-400">{game.eliminated.length} champion(s) eliminated</div>
        )}
      </div>
      <Link to="/wheels" className="btn-secondary" onClick={() => setGame(null)}>
        View
      </Link>
      <button aria-label="Dismiss" className="text-slate-400 hover:text-white" onClick={() => setGame(null)}>
        ✕
      </button>
    </div>
  )
}
