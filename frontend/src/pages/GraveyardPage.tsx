import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { PlayerLink } from '../components/PlayerLink'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState } from '../components/ui'
import { useActiveRun, usePlayerMap } from '../hooks/queries'
import { formatDuration } from '../lib/queues'
import { CLASS_COLORS } from '../lib/reel'
import { teamColor } from '../lib/teams'
import type { Graveyard, Headstone, Run } from '../types'

type Sort = 'newest' | 'oldest' | 'longest' | 'quickest' | 'played'
const SORTS: { id: Sort; label: string }[] = [
  { id: 'newest', label: 'Newest' },
  { id: 'oldest', label: 'Oldest' },
  { id: 'longest', label: 'Lived longest' },
  { id: 'quickest', label: 'Fell quickest' },
  { id: 'played', label: 'Most played' },
]

/** The Graveyard (SPEC 21): every champion the run has lost, with how it lived and how it died. */
export function GraveyardPage() {
  const { run, runId } = useActiveRun()
  if (!runId) {
    return (
      <EmptyState title="No active run">
        <Link to="/settings" className="btn-primary">
          Start a run
        </Link>
      </EmptyState>
    )
  }
  if (!run.data) return <LoadingState />
  return <Yard run={run.data} />
}

function Yard({ run }: { run: Run }) {
  const yard = useQuery({ queryKey: ['graveyard', run.id], queryFn: () => api.graveyard(run.id) })
  const [search, setSearch] = useState('')
  const [player, setPlayer] = useState<number | null>(null)
  const [sort, setSort] = useState<Sort>('newest')
  const g = yard.data
  const shown = useMemo(() => (g ? sortStones(filterStones(g.headstones, search, player), sort) : []), [g, search, player, sort])

  if (yard.isPending) return <LoadingState />
  if (yard.error) return <ErrorText error={yard.error} />
  if (!g) return null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="broadcast-tag" style={{ ['--tag' as string]: '#5b5a56' } as CSSProperties}>
          R.I.P.
        </span>
        <h1 className="text-lg text-white">Graveyard</h1>
        <span className="text-sm text-slate-400">
          {g.dead} of {g.total} champions fallen in {run.name}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]" aria-hidden>
        <div className="h-full rounded-full bg-gradient-to-r from-red-700 to-red-500" style={{ width: `${g.total ? (g.dead / g.total) * 100 : 0}%` }} />
      </div>

      {g.dead === 0 ? (
        <EmptyState title="Nobody's buried here yet">
          <p className="max-w-md text-sm text-slate-400">Every champion lost in this run gets a headstone here: who lost it, its last game and how long it lasted.</p>
        </EmptyState>
      ) : (
        <>
          <Summary g={g} />
          {g.risen.length > 0 && <RisenStrip g={g} />}
          <div className="flex flex-wrap items-center gap-2">
            <input
              className="input w-full sm:w-56"
              placeholder="Search the graves"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search champions"
            />
            <div className="flex flex-wrap gap-1.5">
              <FilterChip active={player === null} onClick={() => setPlayer(null)}>
                Everyone
              </FilterChip>
              {g.diggers.map((d) => (
                <FilterChip key={d.player_id} active={player === d.player_id} onClick={() => setPlayer(player === d.player_id ? null : d.player_id)} color={teamColor(d.player_id)}>
                  <DiggerName id={d.player_id} /> · {d.count}
                </FilterChip>
              ))}
            </div>
            <select className="input ml-auto w-auto py-1 text-sm" value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort">
              {SORTS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          {shown.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">No graves match.</p>
          ) : (
            <ol className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,210px),1fr))] gap-3">
              {shown.map((h) => (
                <Tombstone key={h.champion_id} h={h} />
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  )
}

function filterStones(list: Headstone[], search: string, player: number | null) {
  const q = search.trim().toLowerCase()
  return list.filter((h) => (player === null || h.player_id === player) && (!q || h.name.toLowerCase().includes(q) || h.champion_id.toLowerCase().includes(q)))
}

function sortStones(list: Headstone[], sort: Sort) {
  const at = (h: Headstone) => h.eliminated_at ?? ''
  const out = [...list]
  if (sort === 'newest') out.sort((a, b) => at(b).localeCompare(at(a)))
  if (sort === 'oldest') out.sort((a, b) => at(a).localeCompare(at(b)))
  if (sort === 'longest') out.sort((a, b) => b.games_survived - a.games_survived || at(a).localeCompare(at(b)))
  if (sort === 'quickest') out.sort((a, b) => a.games_survived - b.games_survived || at(a).localeCompare(at(b)))
  if (sort === 'played') out.sort((a, b) => b.played - a.played || b.wins - a.wins)
  return out
}

function DiggerName({ id }: { id: number }) {
  return <>{usePlayerMap().get(id)?.display_name ?? `Player ${id}`}</>
}

function FilterChip({ active, onClick, children, color }: { active: boolean; onClick: () => void; children: ReactNode; color?: string }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-sm px-3 py-1 text-xs font-semibold whitespace-nowrap ring-1 transition duration-150 ring-inset active:scale-95 ${
        active ? 'bg-hex-500/40 text-white ring-hex-300/70' : 'bg-black/25 text-slate-300 ring-white/10 hover:text-slate-100 hover:ring-hex-400/50'
      }`}
    >
      {color && <span className="h-2 w-2 rounded-full" style={{ background: color }} aria-hidden />}
      {children}
    </button>
  )
}

function Summary({ g }: { g: Graveyard }) {
  const byId = new Map(g.headstones.map((h) => [h.champion_id, h]))
  const most = g.diggers[0]?.count ?? 0
  const longest = g.longest ? byId.get(g.longest) : undefined
  const quickest = g.quickest ? byId.get(g.quickest) : undefined
  const feature = (label: string, id: string | null, caption: (h: Headstone) => string) => {
    const h = id ? byId.get(id) : undefined
    return (
      <section className="card flex items-center gap-3 p-3">
        {h ? <ChampionPortrait champion={h} size="sm" dim className="!opacity-70" /> : <div className="h-10 w-10 rounded-md bg-slate-800" />}
        <div className="flex min-w-0 flex-col">
          <span className="text-[11px] font-bold tracking-[0.14em] text-slate-500 uppercase">{label}</span>
          <span className="truncate text-sm font-semibold text-white">{h?.name ?? '-'}</span>
          {h && <span className="truncate text-xs text-slate-400">{caption(h)}</span>}
        </div>
      </section>
    )
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <section className="card flex flex-col gap-1.5 p-3 sm:row-span-2 lg:row-span-1">
        <span className="text-[11px] font-bold tracking-[0.14em] text-slate-500 uppercase">Gravediggers</span>
        <ol className="flex flex-col gap-1">
          {g.diggers.slice(0, 5).map((d) => (
            <li key={d.player_id} className="flex items-center gap-2 text-sm">
              <PlayerLink id={d.player_id} className="w-20 truncate text-slate-200" />
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                <span className="block h-full rounded-full" style={{ width: `${(d.count / most) * 100}%`, background: teamColor(d.player_id) }} />
              </span>
              <span className="w-5 text-right text-slate-300 tabular-nums">{d.count}</span>
            </li>
          ))}
        </ol>
        {g.by_class.length > 0 && (
          <p className="text-xs text-slate-500">
            Hardest hit:{' '}
            <span style={{ color: CLASS_COLORS[g.by_class[0].tag] ?? undefined }}>{g.by_class[0].tag}s</span> ({g.by_class[0].count})
          </p>
        )}
      </section>
      {feature('First blood', g.first_blood, (h) => `Game ${h.game_number}`)}
      {feature('Quickest fall', g.quickest, (h) => (h.games_survived === 0 ? 'Fell in the first game' : `After ${h.games_survived} ${h.games_survived === 1 ? 'game' : 'games'}`))}
      {longest && longest.games_survived > (quickest?.games_survived ?? 0)
        ? feature('Longest life', g.longest, (h) => `Lived through ${h.games_survived} ${h.games_survived === 1 ? 'game' : 'games'}`)
        : feature('Last to fall', g.headstones[0]?.champion_id ?? null, (h) => (h.manual ? 'Removed by hand' : `Game ${h.game_number}`))}
    </div>
  )
}

function RisenStrip({ g }: { g: Graveyard }) {
  return (
    <section className="card flex flex-wrap items-center gap-x-4 gap-y-2 p-3">
      <span className="text-[11px] font-bold tracking-[0.14em] text-gold-300 uppercase">Back from the dead</span>
      {g.risen.map((r) => (
        <span key={r.champion_id} className="flex items-center gap-2 text-sm text-slate-200" title={`Revived ${r.revived}x, died ${r.deaths}x`}>
          <ChampionPortrait champion={r} size="xs" />
          {r.name}
          {r.revived > 1 && <span className="text-xs text-gold-300">×{r.revived}</span>}
        </span>
      ))}
    </section>
  )
}

function Tombstone({ h }: { h: Headstone }) {
  const lg = h.last_game
  const color = h.player_id != null ? teamColor(h.player_id) : '#5b5a56'
  const date = h.eliminated_at ? new Date(h.eliminated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : null
  return (
    <li
      className="relative flex flex-col items-center gap-2 overflow-hidden bg-gradient-to-b from-slate-700/70 to-slate-800/80 px-4 pt-6 pb-4 text-center shadow-[0_8px_24px_-12px_rgba(0,0,0,0.8)] ring-1 ring-white/10 ring-inset"
      style={{ borderRadius: '50% 50% 6px 6px / 72px 72px 6px 6px' }}
    >
      <span className="text-[10px] font-bold tracking-[0.3em] text-slate-400">R.I.P.</span>
      <ChampionPortrait champion={h} size="lg" className="rounded-full grayscale ring-2 ring-black/40" />
      <div className="flex flex-col">
        <span className="font-display text-xl leading-tight text-white">{h.name}</span>
        {h.title && <span className="text-[11px] text-slate-400 capitalize">{h.title}</span>}
      </div>
      <span className="text-xs text-slate-300">
        {h.manual ? (
          'Removed by hand'
        ) : (
          <>
            Game {h.game_number}
            {h.player_id != null && (
              <>
                {' · '}
                <PlayerLink id={h.player_id} className="font-semibold" />
              </>
            )}
          </>
        )}
        {date && <span className="text-slate-500"> · {date}</span>}
      </span>
      {lg && (
        <span className="rounded-sm bg-black/30 px-2 py-0.5 text-xs text-slate-200 tabular-nums">
          {lg.kills}/{lg.deaths}/{lg.assists}
          {lg.grade && <b className="ml-1.5 text-gold-300">{lg.grade}</b>}
          {lg.duration > 0 && <span className="ml-1.5 text-slate-400">{formatDuration(lg.duration)}</span>}
        </span>
      )}
      <p className="min-h-[2.5em] text-sm text-slate-300 italic">“{h.epitaph}”</p>
      <dl className="grid w-full grid-cols-3 gap-1 border-t border-white/10 pt-2 text-[11px] text-slate-400">
        <Fact label="Lived" value={`${h.games_survived}g`} />
        <Fact label="Record" value={`${h.wins}-${h.losses}`} />
        <Fact label="Rolled" value={`${h.played}/${h.offered}`} title={`Played ${h.played} of the ${h.offered} times it was offered`} />
      </dl>
      {(h.revived > 0 || h.shields_broken > 0 || h.deaths > 1) && (
        <div className="flex flex-wrap justify-center gap-1.5 text-[11px]">
          {h.revived > 0 && <span className="rounded-sm bg-gold-500/15 px-1.5 py-0.5 text-gold-200">Revived ×{h.revived}</span>}
          {h.deaths > 1 && <span className="rounded-sm bg-red-500/15 px-1.5 py-0.5 text-red-200">Died ×{h.deaths}</span>}
          {h.shields_broken > 0 && <span className="rounded-sm bg-hex-500/20 px-1.5 py-0.5 text-hex-100">Shields ×{h.shields_broken}</span>}
        </div>
      )}
      <span className="absolute inset-x-0 bottom-0 h-1" style={{ background: color }} aria-hidden />
    </li>
  )
}

function Fact({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="flex flex-col" title={title}>
      <dt>{label}</dt>
      <dd className="text-sm font-semibold text-slate-100 tabular-nums">{value}</dd>
    </div>
  )
}
