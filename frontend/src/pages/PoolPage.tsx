import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ChampionCard } from '../components/ChampionCard'
import { PoolCard, type CardAction } from '../components/PoolCard'
import { EmptyState, ErrorText, LoadingState } from '../components/ui'
import { useActiveRun, useChampionLines, useEconomy, usePlayerMap, usePool } from '../hooks/queries'
import { docRect, flyCardTo } from '../lib/cardFlight'
import {
  POOL_SORTS,
  QUICK_FILTERS,
  allTags,
  filterChampions,
  loadingUrl,
  matchesQuick,
  sortPool,
  type PoolSort,
  type QuickFilter,
} from '../lib/champions'
import { CLASS_COLORS } from '../lib/reel'
import type { ChampionLine, PoolEntry, Run } from '../types'

const SIZE_KEY = 'lol-survival:pool-card-size'
const DEAD_OPEN_KEY = 'lol-survival:pool-eliminated-open'
const SORT_KEY = 'lol-survival:pool-sort'
const NO_LINES: Record<string, ChampionLine> = {}

function readPref<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key) as T | null
    return v && allowed.includes(v) ? v : fallback
  } catch {
    return fallback
  }
}

function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* per-viewer convenience only */
  }
}

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
  return <Pool run={run.data} />
}

function Chip({
  active,
  onClick,
  children,
  color,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
  color?: string
}) {
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

function Pool({ run }: { run: Run }) {
  const pool = usePool(run.id)
  const linesQuery = useChampionLines(run.id)
  const economy = useEconomy(run.id)
  const players = usePlayerMap()
  const [search, setSearch] = useState('')
  const [tag, setTag] = useState<string | null>(null)
  const [quick, setQuick] = useState<QuickFilter | null>(null)
  const [sort, setSort] = useState<PoolSort>(() => readPref(SORT_KEY, POOL_SORTS.map((s) => s.id), 'name'))
  const [compact, setCompact] = useState(() => readPref(SIZE_KEY, ['large', 'compact'] as const, 'large') === 'compact')
  const [deadOpen, setDeadOpen] = useState(() => readPref(DEAD_OPEN_KEY, ['1', '0'] as const, '1') === '1')
  const [open, setOpen] = useState<{ entry: PoolEntry; focus?: CardAction } | null>(null)
  const aliveRef = useRef<HTMLDivElement>(null)
  const deadRef = useRef<HTMLDivElement>(null)

  useEffect(() => writePref(SORT_KEY, sort), [sort])
  useEffect(() => writePref(SIZE_KEY, compact ? 'compact' : 'large'), [compact])
  useEffect(() => writePref(DEAD_OPEN_KEY, deadOpen ? '1' : '0'), [deadOpen])

  const lines = linesQuery.data ?? NO_LINES
  const entries = useMemo(() => pool.data ?? [], [pool.data])
  const active = run.status === 'active'
  const canRevive = active && run.tokens_available > 0
  const canShield = active && (economy.data ?? []).some((e) => (e.unused.shield ?? 0) > 0)

  // Search + quick filter first; class counts are taken from that, then the class filter applies.
  const searched = useMemo(
    () => filterChampions(entries, search).filter((e) => matchesQuick(e, lines[e.champion_id], quick)),
    [entries, search, quick, lines],
  )
  const tags = useMemo(() => allTags(entries), [entries])
  const tagCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const e of searched) for (const t of e.tags) m.set(t, (m.get(t) ?? 0) + 1)
    return m
  }, [searched])
  const shown = useMemo(() => sortPool(tag ? searched.filter((e) => e.tags.includes(tag)) : searched, lines, sort), [searched, tag, lines, sort])
  const alive = useMemo(() => shown.filter((e) => e.status === 'alive'), [shown])
  const dead = useMemo(() => shown.filter((e) => e.status === 'eliminated'), [shown])
  const deadTotal = run.total_count - run.alive_count
  const filtering = search.trim() !== '' || tag !== null || quick !== null
  const clear = () => (setSearch(''), setTag(null), setQuick(null))

  const onOpen = useCallback((e: PoolEntry) => setOpen({ entry: e }), [])
  const onAction = useCallback((e: PoolEntry, focus: CardAction) => setOpen({ entry: e, focus }), [])

  const onRevived = (e: PoolEntry) => {
    // The Eliminated card is still on the page at this point (the pool refreshes right after).
    const src = deadRef.current?.querySelector(`[data-card-id="${CSS.escape(e.champion_id)}"]`)
    const from = src ? docRect(src) : null
    // Make sure the card is visible in the Alive grid even if filters would hide it.
    if (filtering) clear()
    if (aliveRef.current) {
      void flyCardTo({ root: aliveRef.current, id: e.champion_id, imageUrl: loadingUrl(e), from })
    }
  }

  const grid = `grid gap-3 ${
    compact ? 'grid-cols-[repeat(auto-fill,minmax(104px,1fr))]' : 'grid-cols-2 sm:grid-cols-[repeat(auto-fill,minmax(158px,1fr))]'
  }`
  const card = (e: PoolEntry) => (
    <PoolCard
      key={e.champion_id}
      entry={e}
      line={lines[e.champion_id]}
      players={players}
      compact={compact}
      action={e.status === 'eliminated' ? (canRevive ? 'revive' : null) : canShield && !e.shield_item_id ? 'shield' : null}
      onOpen={onOpen}
      onAction={onAction}
    />
  )

  return (
    <div className="flex flex-col gap-5">
      {/* Header + summary */}
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-gold-100">Champion Pool</h1>
        <p className="text-sm text-slate-400">
          <b className="text-hex-200">{run.alive_count}</b> alive · <b className="text-slate-200">{deadTotal}</b> eliminated
          {run.shielded_count > 0 && (
            <>
              {' '}
              · <b className="text-emerald-300">{run.shielded_count}</b> shielded
            </>
          )}{' '}
          · <b className="text-gold-300">{run.tokens_available}</b> revive token{run.tokens_available === 1 ? '' : 's'}
        </p>
      </div>

      {/* Toolbar */}
      <div className="glass flex flex-col gap-3 rounded-2xl p-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="input min-w-0 flex-1 sm:max-w-64"
            placeholder="Find a champion..."
            aria-label="Search champions"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select className="input" aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value as PoolSort)}>
            {POOL_SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <div className="ml-auto inline-flex rounded-sm bg-black/30 p-1 ring-1 ring-white/10 ring-inset" role="group" aria-label="Card size">
            {(['large', 'compact'] as const).map((v) => (
              <button
                key={v}
                aria-pressed={(v === 'compact') === compact}
                onClick={() => setCompact(v === 'compact')}
                className={`rounded-sm px-3 py-1 text-sm capitalize transition duration-150 ${
                  (v === 'compact') === compact ? 'bg-hex-500/60 text-white' : 'text-slate-400 hover:text-slate-100'
                }`}
              >
                {v}
              </button>
            ))}
          </div>
        </div>
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-0.5" role="group" aria-label="Class">
          <Chip active={tag === null} onClick={() => setTag(null)}>
            All <span className="opacity-60">{searched.length}</span>
          </Chip>
          {tags.map((t) => (
            <Chip key={t} active={tag === t} onClick={() => setTag(tag === t ? null : t)} color={CLASS_COLORS[t]}>
              {t} <span className="opacity-60">{tagCounts.get(t) ?? 0}</span>
            </Chip>
          ))}
        </div>
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-0.5" role="group" aria-label="Quick filters">
          {QUICK_FILTERS.map((f) => (
            <Chip key={f.id} active={quick === f.id} onClick={() => setQuick(quick === f.id ? null : f.id)}>
              {f.label}
            </Chip>
          ))}
          {filtering && (
            <button className="ml-auto shrink-0 px-2 text-xs text-slate-400 underline hover:text-slate-200" onClick={clear}>
              Clear filters
            </button>
          )}
        </div>
      </div>

      {canRevive && deadTotal > 0 && (
        <p className="glass rounded-2xl px-4 py-2.5 text-sm text-gold-200">
          ✦ You have {run.tokens_available} revive token{run.tokens_available > 1 ? 's' : ''}. Hit Revive on an eliminated
          champion to bring them back.
        </p>
      )}
      {pool.isLoading && <LoadingState />}
      <ErrorText error={pool.error ?? linesQuery.error} />

      {pool.isSuccess && (
        <>
          <section className="flex flex-col gap-3">
            <h2 className="flex items-baseline gap-2 px-1 text-lg font-bold text-hex-100">
              Alive
              <span className="font-sans text-sm font-medium text-slate-400">
                {filtering ? `${alive.length} of ${run.alive_count}` : run.alive_count}
              </span>
            </h2>
            <div ref={aliveRef} className={grid}>
              {alive.map(card)}
            </div>
            {alive.length === 0 && (
              <p className="px-1 text-sm text-slate-400">
                {filtering ? 'No alive champions match.' : 'Nobody left. Every champ has been eliminated.'}
              </p>
            )}
          </section>

          <section className="flex flex-col gap-3">
            <button
              type="button"
              onClick={() => setDeadOpen((o) => !o)}
              aria-expanded={deadOpen}
              className="flex items-baseline gap-2 self-start px-1 text-lg font-bold text-slate-300 hover:text-slate-100"
            >
              <span className={`inline-block text-sm transition-transform duration-150 ${deadOpen ? 'rotate-90' : ''}`} aria-hidden>
                ▸
              </span>
              Eliminated
              <span className="font-sans text-sm font-medium text-slate-400">
                {filtering ? `${dead.length} of ${deadTotal}` : deadTotal}
              </span>
            </button>
            {deadOpen && (
              <>
                <div ref={deadRef} className={grid}>
                  {dead.map(card)}
                </div>
                {dead.length === 0 && (
                  <p className="px-1 text-sm text-slate-400">
                    {filtering ? 'No eliminated champions match.' : 'Nobody yet. Champs end up here when you lose with them.'}
                  </p>
                )}
              </>
            )}
          </section>
        </>
      )}

      {open && (
        <ChampionCard
          run={run}
          entry={open.entry}
          focus={open.focus}
          onRevived={onRevived}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}
