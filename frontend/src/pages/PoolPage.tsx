import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ChampionPortrait, EmptyState, ErrorText, Modal } from '../components/ui'
import { useAction, useActiveRun, usePlayerMap, usePool, useTokens } from '../hooks/queries'
import { allTags, filterChampions } from '../lib/champions'
import type { PoolEntry, Run } from '../types'

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
  if (!run.data) return <p className="text-slate-400">Loading...</p>
  return <Pool run={run.data} />
}

function Pool({ run }: { run: Run }) {
  const pool = usePool(run.id)
  const players = usePlayerMap()
  const [search, setSearch] = useState('')
  const [tag, setTag] = useState<string | null>(null)
  const [showEliminated, setShowEliminated] = useState(true)
  const [selected, setSelected] = useState<PoolEntry | null>(null)

  const entries = pool.data ?? []
  const tags = useMemo(() => allTags(entries), [entries])
  const shown = filterChampions(entries, search, tag).filter((e) => showEliminated || e.status === 'alive')

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">
          <span className="text-gold-400">{run.alive_count}</span> alive / {run.total_count} total
        </h1>
        <input
          className="input w-48"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="input" value={tag ?? ''} onChange={(e) => setTag(e.target.value || null)}>
          <option value="">All classes</option>
          {tags.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={showEliminated} onChange={(e) => setShowEliminated(e.target.checked)} />
          Show eliminated
        </label>
      </div>
      {run.tokens_available > 0 && (
        <p className="text-sm text-gold-300">
          {run.tokens_available} revive token(s) available. Click an eliminated champion to revive it.
        </p>
      )}

      <div className="grid grid-cols-[repeat(auto-fill,minmax(80px,1fr))] gap-3">
        {shown.map((e) => {
          const dead = e.status === 'eliminated'
          const by = e.eliminated_by_player_id ? players.get(e.eliminated_by_player_id)?.display_name : null
          return (
            <button
              key={e.champion_id}
              onClick={() => setSelected(e)}
              className="group flex flex-col items-center gap-1 rounded-lg p-1 hover:bg-slate-800"
              title={dead ? `Eliminated${by ? ` (played by ${by})` : ''}` : e.name}
            >
              <div className="relative">
                <ChampionPortrait champion={e} size="lg" dim={dead} />
                {dead && <span className="absolute inset-0 flex items-center justify-center text-3xl text-red-500/80">✕</span>}
              </div>
              <span className={`w-full truncate text-center text-xs ${dead ? 'text-slate-500 line-through' : ''}`}>
                {e.name}
              </span>
              {dead && by && <span className="w-full truncate text-center text-[10px] text-slate-500">{by}</span>}
            </button>
          )
        })}
      </div>
      {pool.isSuccess && shown.length === 0 && <p className="text-slate-400">No champions match.</p>}
      {selected && <ChampionActions run={run} entry={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

function ChampionActions({ run, entry, onClose }: { run: Run; entry: PoolEntry; onClose: () => void }) {
  const players = usePlayerMap()
  const tokens = useTokens(run.id)
  const done = { onSuccess: onClose }
  const eliminate = useAction(() => api.eliminate(run.id, entry.champion_id))
  const revive = useAction((tokenId?: number) => api.revive(run.id, entry.champion_id, tokenId))
  const dead = entry.status === 'eliminated'
  const active = run.status === 'active'
  const by = entry.eliminated_by_player_id ? players.get(entry.eliminated_by_player_id)?.display_name : null

  // One button per player that holds a token
  const tokenByPlayer = new Map<number, number>()
  for (const t of tokens.data ?? []) if (!tokenByPlayer.has(t.player_id)) tokenByPlayer.set(t.player_id, t.id)

  return (
    <Modal title={entry.name} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <ChampionPortrait champion={entry} size="lg" dim={dead} />
          <div className="text-sm">
            <p className="text-slate-400">{entry.title}</p>
            <p>{entry.tags.join(' · ')}</p>
            {dead && (
              <p className="mt-1 text-red-300">
                Eliminated{by && <> (played by {by})</>}
                {entry.eliminated_at && <> on {new Date(entry.eliminated_at).toLocaleString()}</>}
                {entry.eliminated_in_game_id && <> in game #{entry.eliminated_in_game_id}</>}
              </p>
            )}
          </div>
        </div>

        {active && dead && (
          <div className="flex flex-col gap-2">
            {tokenByPlayer.size > 0 ? (
              <>
                <p className="text-sm font-semibold">Revive with a token:</p>
                <div className="flex flex-wrap gap-2">
                  {[...tokenByPlayer].map(([pid, tid]) => (
                    <button key={tid} className="btn-primary" disabled={revive.isPending} onClick={() => revive.mutate(tid, done)}>
                      Use {players.get(pid)?.display_name}'s token
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-400">No revive tokens available.</p>
            )}
          </div>
        )}

        {active && (
          <details className="text-sm">
            <summary className="cursor-pointer text-slate-400">Fix a mistake</summary>
            <div className="mt-2 flex gap-2">
              {dead ? (
                <button className="btn-secondary" disabled={revive.isPending} onClick={() => revive.mutate(undefined, done)}>
                  Manual revive (no token)
                </button>
              ) : (
                <button className="btn-danger" disabled={eliminate.isPending} onClick={() => eliminate.mutate(undefined, done)}>
                  Manual eliminate
                </button>
              )}
            </div>
            <p className="mt-1 text-xs text-slate-500">Manual changes are logged.</p>
          </details>
        )}
        <ErrorText error={eliminate.error ?? revive.error} />
      </div>
    </Modal>
  )
}
