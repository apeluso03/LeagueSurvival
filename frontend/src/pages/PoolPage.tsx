import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { Link } from 'react-router-dom'
import { ChampionCard } from '../components/ChampionCard'
import { ChampionPool } from '../components/ChampionPool'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState } from '../components/ui'
import { useActiveRun, usePlayerMap, usePool } from '../hooks/queries'
import { allTags, filterChampions } from '../lib/champions'
import { flyIntoPool, splash } from '../lib/flight'
import { BUBBLE_PX, type Point } from '../lib/poolLayout'
import type { PoolEntry, Run } from '../types'

const VIEW_KEY = 'lol-survival:pool-view'

export function PoolPage() {
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
  return <Pools run={run.data} />
}

function readView(): 'pools' | 'grid' {
  try {
    return localStorage.getItem(VIEW_KEY) === 'grid' ? 'grid' : 'pools'
  } catch {
    return 'pools'
  }
}

function Pools({ run }: { run: Run }) {
  const pool = usePool(run.id)
  const [search, setSearch] = useState('')
  const [tag, setTag] = useState<string | null>(null)
  const [view, setView] = useState<'pools' | 'grid'>(readView)
  const [open, setOpen] = useState<{ entry: PoolEntry; reviveOnly: boolean } | null>(null)
  const [hint, setHint] = useState<string | null>(null)
  const waterRef = useRef<HTMLDivElement>(null)
  const graveRef = useRef<HTMLDivElement>(null)
  // Revive flight: where a dragged champion was dropped, and where revived ones should land.
  const lastDrop = useRef<{ id: string; point: Point } | null>(null)
  const [arrivals, setArrivals] = useState<Map<string, Point>>(new Map())

  const onRevived = (e: PoolEntry) => {
    const water = waterRef.current
    if (view !== 'pools' || !water) return
    // The Graveyard bubble is still on the page at this point (the pool refreshes right after).
    const src = graveRef.current
      ?.querySelector<HTMLElement>(`[data-id="${CSS.escape(e.champion_id)}"]`)
      ?.getBoundingClientRect()
    const drop = lastDrop.current?.id === e.champion_id ? lastDrop.current.point : null
    lastDrop.current = null
    if (drop) {
      const r = water.getBoundingClientRect()
      setArrivals((m) => new Map(m).set(e.champion_id, { x: drop.x - r.left - BUBBLE_PX / 2, y: drop.y - r.top - BUBBLE_PX / 2 }))
    }
    if (!src) return
    void flyIntoPool({
      pool: water,
      id: e.champion_id,
      imageUrl: e.image_url,
      fromDoc: { x: src.left + src.width / 2 + window.scrollX, y: src.top + src.height / 2 + window.scrollY },
      onSplash: (x, y) => splash(water, x, y, true),
    })
  }

  useEffect(() => {
    try {
      localStorage.setItem(VIEW_KEY, view)
    } catch {
      /* per-viewer convenience only */
    }
  }, [view])

  useEffect(() => {
    if (!hint) return
    const t = setTimeout(() => setHint(null), 3500)
    return () => clearTimeout(t)
  }, [hint])

  const entries = useMemo(() => pool.data ?? [], [pool.data])
  const tags = useMemo(() => allTags(entries), [entries])
  const alive = useMemo(() => entries.filter((e) => e.status === 'alive'), [entries])
  const dead = useMemo(() => entries.filter((e) => e.status === 'eliminated'), [entries])
  const filtering = search.trim() !== '' || tag !== null
  const matches = useMemo(() => new Set(filterChampions(entries, search, tag).map((e) => e.champion_id)), [entries, search, tag])
  const highlight = (e: PoolEntry) => (filtering ? matches.has(e.champion_id) : null)

  const inside = (ref: RefObject<HTMLDivElement | null>, p: Point) => {
    const r = ref.current?.getBoundingClientRect()
    return !!r && p.x >= r.left && p.x <= r.right && p.y >= r.top && p.y <= r.bottom
  }

  // Graveyard -> Pool is a revive (needs a token). Anything else just floats back.
  const dropFromGrave = (e: PoolEntry, p: Point) => {
    if (!inside(waterRef, p)) return false
    if (run.status !== 'active') return setHint('This run has ended.'), false
    if (run.tokens_available === 0) {
      setHint(`No revive tokens yet. Win 3 in a row to get one, then drag ${e.name} back in.`)
      return false
    }
    lastDrop.current = { id: e.champion_id, point: p }
    setOpen({ entry: e, reviveOnly: true })
    return true
  }
  const dropFromWater = (_e: PoolEntry, p: Point) => {
    if (inside(graveRef, p)) setHint('Champs only end up in the Graveyard when you lose with them.')
    return false
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-2xl font-bold text-gold-100">
          <span className="gold-text">{run.alive_count}</span>
          <span className="text-slate-400"> / {run.total_count}</span>
          <span className="ml-2 font-sans text-sm font-medium text-slate-400">alive</span>
        </h1>
        <input
          className="input w-full sm:w-52"
          placeholder="Find a champion..."
          aria-label="Search champions"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="input" aria-label="Class" value={tag ?? ''} onChange={(e) => setTag(e.target.value || null)}>
          <option value="">All classes</option>
          {tags.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <div className="inline-flex rounded-full bg-black/30 p-1 ring-1 ring-gold-700/25 ring-inset" role="group" aria-label="View">
          {(['pools', 'grid'] as const).map((v) => (
            <button
              key={v}
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={`rounded-full px-3 py-1 text-sm capitalize transition duration-150 ${
                view === v ? 'bg-gold-700/50 text-gold-100' : 'text-slate-400 hover:text-slate-100'
              }`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {run.tokens_available > 0 && dead.length > 0 && (
        <p className="glass rounded-2xl px-4 py-2.5 text-sm text-gold-200">
          ✦ You have {run.tokens_available} revive token{run.tokens_available > 1 ? 's' : ''}. Drag someone from the
          Graveyard back into the Pool to use one.
        </p>
      )}
      {hint && (
        <p role="status" className="fade-in glass rounded-2xl px-4 py-2.5 text-sm text-slate-200">
          {hint}
        </p>
      )}
      {pool.isLoading && <LoadingState />}
      <ErrorText error={pool.error} />
      {filtering && matches.size === 0 && (
        <p className="text-sm text-slate-400">
          No champions match.{' '}
          <button className="underline" onClick={() => (setSearch(''), setTag(null))}>
            Clear filters
          </button>
        </p>
      )}

      {pool.isSuccess &&
        (view === 'pools' ? (
          <>
            <ChampionPool
              entries={alive}
              variant="water"
              poolRef={waterRef}
              title="The Pool"
              subtitle="Drag them around, or tap one for info"
              highlight={highlight}
              onOpen={(e) => setOpen({ entry: e, reviveOnly: false })}
              onDropOutside={dropFromWater}
              arrivals={arrivals}
              empty="Nobody left. Every champ has been eliminated."
            />
            <ChampionPool
              entries={dead}
              variant="grave"
              poolRef={graveRef}
              title="The Graveyard"
              subtitle={dead.length ? `${dead.length} eliminated` : undefined}
              highlight={highlight}
              onOpen={(e) => setOpen({ entry: e, reviveOnly: false })}
              onDropOutside={dropFromGrave}
              empty="Empty for now. Champs end up here when you lose with them."
            />
          </>
        ) : (
          <Grid entries={entries} highlight={highlight} onOpen={(e) => setOpen({ entry: e, reviveOnly: false })} />
        ))}

      {open && (
        <ChampionCard
          run={run}
          entry={open.entry}
          reviveOnly={open.reviveOnly}
          onRevived={onRevived}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}

function Grid({
  entries,
  highlight,
  onOpen,
}: {
  entries: PoolEntry[]
  highlight: (e: PoolEntry) => boolean | null
  onOpen: (e: PoolEntry) => void
}) {
  const players = usePlayerMap()
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(84px,1fr))] gap-2">
      {entries.map((e) => {
        const dead = e.status === 'eliminated'
        const by = e.eliminated_by_player_id ? players.get(e.eliminated_by_player_id)?.display_name : null
        const hl = highlight(e)
        return (
          <button
            key={e.champion_id}
            onClick={() => onOpen(e)}
            className="flex flex-col items-center gap-1 rounded-2xl p-1.5 transition duration-150 hover:bg-white/5 active:scale-95"
            style={{ opacity: hl === false ? 0.2 : 1 }}
            title={dead ? `Eliminated${by ? ` (${by})` : ''}` : e.name}
          >
            <ChampionPortrait champion={e} size="lg" dim={dead} className="rounded-2xl" />
            <span className={`w-full truncate text-center text-xs ${dead ? 'text-slate-500 line-through' : ''}`}>{e.name}</span>
          </button>
        )
      })}
    </div>
  )
}
