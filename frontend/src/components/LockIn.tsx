import { useEffect, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { useChampionMap, usePlayerMap, usePool } from '../hooks/queries'
import { loadingUrl } from '../lib/champions'
import { playLockIn } from '../lib/sound'
import type { CompPick, Game } from '../types'
import { teamColor } from '../lib/teams'
import { ShieldIcon } from './icons'
import { LowerThird } from './LowerThird'
import { BroadcastBanner, ReplayChrome } from './ReplayChrome'
import { BuildStrip, RoleChip } from './BuildStrip'

const LOCK_MS = 2600

function usePicks(game: Game) {
  const champs = useChampionMap()
  const players = usePlayerMap()
  return game.assignments.map((a) => {
    const champ = a.played_champion_id ? champs.get(a.played_champion_id) : undefined
    return {
      playerId: a.player_id,
      player: players.get(a.player_id)?.display_name ?? `Player ${a.player_id}`,
      champ,
      art: champ ? loadingUrl({ champion_id: champ.id, image_url: champ.image_url }) : null,
      pick: a.played_option_index != null ? `Pick #${a.played_option_index + 1}` : 'Other',
    }
  })
}

/** Everyone has picked: a short champ-select style "LOCKED IN" with the picks fanned out. */
export function LockInMoment({ game, onDone }: { game: Game; onDone: () => void }) {
  const picks = usePicks(game)
  useEffect(() => {
    playLockIn()
    const t = setTimeout(onDone, LOCK_MS)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onDone()
    window.addEventListener('keydown', onKey)
    return () => (clearTimeout(t), window.removeEventListener('keydown', onKey))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game.id])
  const mid = (picks.length - 1) / 2
  return createPortal(
    <div className="lockin-overlay fixed inset-0 z-[80] flex flex-col items-center justify-center gap-8 overflow-hidden bg-[#05070b]/95 p-4" onClick={onDone} role="dialog" aria-label="Locked in">
      <div className="flex items-end justify-center">
        {picks.map((p, i) => (
          <div
            key={p.playerId}
            className="lockin-card -mx-3 flex flex-col items-center gap-2 sm:mx-1"
            style={{ '--i': i, '--rot': `${(i - mid) * 5}deg`, '--lift': `${Math.abs(i - mid) * 10}px` } as CSSProperties}
          >
            <div className="loading-frame w-24 sm:w-36" style={{ backgroundImage: p.art ? `url(${p.art})` : undefined }} />
            <div className="text-center leading-tight">
              <div className="font-display text-sm font-bold text-gold-100">{p.champ?.name}</div>
              <div className="text-xs text-slate-400">{p.player}</div>
            </div>
          </div>
        ))}
      </div>
      <ReplayChrome tag={`Draft complete · Game ${game.id}`} color="var(--color-hex-500)" />
      <BroadcastBanner color="var(--color-hex-400)" className="lockin-title">
        <h2 className="font-display text-4xl tracking-[0.25em] text-white uppercase sm:text-5xl">Locked in</h2>
      </BroadcastBanner>
    </div>,
    document.body,
  )
}

/** The pending game once everyone has picked, laid out like the in-game loading screen. */
export function LoadingScreen({ game, onEdit, builds }: { game: Game; onEdit: () => void; builds: Map<string, CompPick> }) {
  const picks = usePicks(game)
  const pool = usePool(game.run_id)
  const shielded = new Set((pool.data ?? []).filter((e) => e.shield_item_id).map((e) => e.champion_id))
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-2 px-1">
        <h2 className="text-xs font-semibold tracking-[0.16em] text-slate-400 uppercase">Loading into game {game.id}</h2>
        <button className="text-xs text-slate-400 underline hover:text-slate-200" onClick={onEdit}>
          Change picks
        </button>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:flex sm:justify-center">
        {picks.map((p, i) => (
          <div key={p.playerId} className="reel-land flex flex-col gap-2 sm:w-48" style={{ animationDelay: `${i * 90}ms` }}>
            <div
              className="loading-frame relative w-full"
              style={{ backgroundImage: p.art ? `url(${p.art})` : undefined, ['--team' as string]: teamColor(p.playerId) } as CSSProperties}
            >
              {p.champ && shielded.has(p.champ.id) && (
                <span className="pool-badge absolute top-2 right-2 bg-emerald-600 text-white" title="Shielded: a loss breaks the shield instead">
                  <ShieldIcon className="h-3.5 w-3.5" strokeWidth={2.4} />
                </span>
              )}
              <div className="absolute inset-x-0 bottom-0 flex flex-col gap-1.5 bg-gradient-to-t from-black/95 via-black/75 to-transparent px-2 pt-10 pb-2.5">
                <span className="font-display px-1 text-xl tracking-wide text-white uppercase">{p.champ?.name}</span>
                <LowerThird playerId={p.playerId} name={p.player} sub={p.pick} size="sm" />
              </div>
              <span className="absolute top-2 left-2">
                <RoleChip pick={p.champ ? builds.get(p.champ.id) : undefined} />
              </span>
            </div>
            <div className="rounded-sm bg-white/[0.03] p-2 ring-1 ring-white/[0.06] ring-inset">
              <BuildStrip pick={p.champ ? builds.get(p.champ.id) : undefined} />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
