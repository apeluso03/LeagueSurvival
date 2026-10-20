import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api, isUnreachable } from '../api/client'
import { useAction, useActiveRun, useChampionMap, useChampions, usePlayerMap } from '../hooks/queries'
import { useAccess } from '../hooks/useAuth'
import { TIER_COLORS } from '../lib/tiers'
import { playShieldSave } from '../lib/sound'
import type { AchievementInfo, Game } from '../types'
import { LowerThird } from './LowerThird'
import { EliminationMoment } from './EliminationMoment'
import { WinMoment } from './WinMoment'
import { GoldBadge } from './Gold'
import { ChampionPortrait, ErrorText } from './ui'

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
  const { isSiteAdmin } = useAccess()
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
        {isSiteAdmin && <button className="ml-auto underline" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
          {refresh.isPending ? 'Loading...' : 'Try again'}
        </button>}
        {refresh.error && <span className="w-full text-red-200">{refresh.error.message}</span>}
      </div>
    </div>
  )
}

const RESULT_TEXT: Record<Game['status'], string> = { won: 'Win', lost: 'Loss', void: 'Thrown out', pending: '' }
const TOAST_MS = 15_000

/**
 * Watches the active run's pending game. When it gets a result (from Riot's auto-matcher, the
 * Wheels tab, or another device):
 * - a loss plays the elimination moment, wherever you are;
 * - off the Wheels tab, a toast says what changed, with Undo.
 */
export function ResultWatcher({ toasts = true }: { toasts?: boolean }) {
  const { run } = useActiveRun()
  const { pathname } = useLocation()
  const pendingId = run.data?.pending_game_id ?? null
  const prev = useRef(pendingId)
  const where = useRef(pathname)
  const [toast, setToast] = useState<Game | null>(null)
  const [moment, setMoment] = useState<Game | null>(null)
  const [win, setWin] = useState<{ game: Game; streak: number } | null>(null)
  const [unlocked, setUnlocked] = useState<{ key: number; items: { playerId: number; info: AchievementInfo }[] } | null>(null)

  useEffect(() => {
    where.current = pathname
  }, [pathname])

  useEffect(() => {
    const before = prev.current
    prev.current = pendingId
    if (before == null || pendingId != null) return
    const runId = run.data?.id
    Promise.all([api.game(before), runId != null ? api.run(runId) : Promise.resolve(null), api.achievements()])
      .then(([g, r, report]) => {
        if (g.status === 'pending') return
        const bigMoment = (g.status === 'lost' && g.eliminated.length + g.shields_saved.length > 0) || g.status === 'won'
        if (g.status === 'lost' && g.eliminated.length + g.shields_saved.length > 0) setMoment(g)
        if (g.status === 'won') setWin({ game: g, streak: r?.current_streak ?? 0 })
        if (toasts && where.current !== '/wheels') setToast(g)
        // Achievements this game unlocked, shown once the big moment is over.
        const info = new Map(report.catalog.map((a) => [a.id, a]))
        const items = Object.entries(report.players).flatMap(([pid, list]) =>
          list.filter((u) => u.game_id === g.id && info.has(u.id)).map((u) => ({ playerId: Number(pid), info: info.get(u.id)! })),
        )
        if (items.length) setTimeout(() => setUnlocked({ key: g.id, items }), bigMoment ? ACHIEVEMENT_DELAY_MS : 0)
      })
      .catch(() => {})
    // Only a change of the pending game matters; the run id comes along with it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingId])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), TOAST_MS)
    return () => clearTimeout(t)
  }, [toast])

  return (
    <>
      {moment && <EliminationMoment key={moment.id} game={moment} onDone={() => setMoment(null)} />}
      {win && <WinMoment key={win.game.id} game={win.game} streak={win.streak} onDone={() => setWin(null)} />}
      {toast && <ResultToast game={toast} streak={run.data?.current_streak ?? 0} onClose={() => setToast(null)} />}
      {unlocked && <AchievementPopup key={unlocked.key} items={unlocked.items} onDone={() => setUnlocked(null)} />}
    </>
  )
}

const ACHIEVEMENT_DELAY_MS = 3000
const ACHIEVEMENT_MS = 6500

/** "ACHIEVEMENT UNLOCKED" banner for what a game just earned. */
function AchievementPopup({ items, onDone }: { items: { playerId: number; info: AchievementInfo }[]; onDone: () => void }) {
  useEffect(() => {
    playShieldSave()
    const t = setTimeout(onDone, ACHIEVEMENT_MS)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return (
    <div role="status" className="achievement-popup fixed top-24 left-1/2 z-[85] flex w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 flex-col gap-2 p-3" onClick={onDone}>
      <span className="broadcast-tag self-start" style={{ ['--tag' as string]: 'var(--color-gold-600)' }}>
        Achievement unlocked
      </span>
      {items.slice(0, 4).map(({ playerId, info }) => (
        <div key={`${playerId}-${info.id}`} className="flex items-center gap-3">
          <span className="trophy-icon small" style={{ ['--tier' as string]: TIER_COLORS[info.tier] }} aria-hidden>
            {info.icon}
          </span>
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="font-display tracking-wide text-white uppercase">{info.name}</span>
            <LowerThird playerId={playerId} size="sm" sub={`“${info.title}”`} />
          </div>
        </div>
      ))}
      {items.length > 4 && <span className="text-xs text-slate-400">and {items.length - 4} more · see Trophies</span>}
    </div>
  )
}

function ResultToast({ game, streak, onClose }: { game: Game; streak: number; onClose: () => void }) {
  const champs = useChampionMap()
  const players = usePlayerMap()
  const undo = useAction(() => api.undo(game.id))
  const { canManage } = useAccess()
  const won = game.status === 'won'
  const tone = won ? 'var(--color-hex-300)' : game.status === 'lost' ? '#e5283c' : '#636d80'
  const name = (pid: number | string) => players.get(Number(pid))?.display_name ?? `Player ${pid}`
  const gold = Object.entries(game.gold)

  return (
    <div
      role="status"
      className="toast-in toast-panel fixed right-4 bottom-4 left-4 z-50 mx-auto flex max-w-md flex-col gap-2.5 p-4 sm:left-auto"
      style={{ ['--tone' as string]: tone }}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <span className="broadcast-tag" style={{ ['--tag' as string]: tone }}>
            Final · Game {game.id}
          </span>
          <div className="font-display mt-1.5 text-2xl tracking-wide text-white uppercase">
            {RESULT_TEXT[game.status]}
            {game.result_source === 'auto' && <span className="ml-2 font-sans text-xs tracking-normal text-hex-200 normal-case">from Riot</span>}
          </div>
          <div className="text-sm text-slate-400">
            {won ? `Streak is now ${streak} 🔥` : game.status === 'lost' ? 'Streak reset to 0' : 'Nothing changed'}
          </div>
        </div>
        <button aria-label="Dismiss" className="text-slate-400 hover:text-white" onClick={onClose}>
          ✕
        </button>
      </div>

      {game.eliminated.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-sm">
          <span className="text-red-300">Eliminated:</span>
          {game.eliminated.map((cid) => (
            <span key={cid} className="flex items-center gap-1 rounded-full bg-red-950/60 py-0.5 pr-2 pl-0.5">
              <ChampionPortrait champion={champs.get(cid)} size="xs" dim className="rounded-full" />
              {champs.get(cid)?.name ?? cid}
            </span>
          ))}
        </div>
      )}
      {game.shields_saved.length > 0 && (
        <p className="text-sm text-hex-200">Shield saved {game.shields_saved.map((c) => champs.get(c)?.name ?? c).join(', ')}</p>
      )}
      {game.tokens_earned.length > 0 && (
        <p className="text-sm text-gold-300">✦ Revive token for {game.tokens_earned.map(name).join(', ')}</p>
      )}
      {gold.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {gold.map(([pid, amount]) => (
            <span key={pid} className="flex items-center gap-1.5 rounded-full bg-white/5 px-2.5 py-0.5 text-sm">
              {name(pid)} <GoldBadge amount={amount} />
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2">
        {canManage && (
          <button
            className="btn-secondary"
            disabled={undo.isPending}
            onClick={() => undo.mutate(undefined, { onSuccess: onClose })}
            title="Put the game back to waiting for a result"
          >
            Undo
          </button>
        )}
        <Link to="/wheels" className="btn-secondary" onClick={onClose}>
          View
        </Link>
        <span className="toast-timer ml-auto h-1 w-16 overflow-hidden rounded-full bg-white/10" aria-hidden>
          <span style={{ animationDuration: `${TOAST_MS}ms` }} />
        </span>
      </div>
      <ErrorText error={undo.error} />
    </div>
  )
}
