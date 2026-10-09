import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { MatchSummaryView } from '../components/MatchSummary'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState } from '../components/ui'
import {
  useAction,
  useActiveRun,
  useChampionMap,
  useGames,
  usePlayerMap,
  usePoolEvents,
  useRuns,
} from '../hooks/queries'
import type { Game, PoolEvent, Run } from '../types'

const STATUS_STYLE: Record<Game['status'], string> = {
  won: 'bg-emerald-500/15 text-emerald-300',
  lost: 'bg-red-500/15 text-red-300',
  void: 'bg-slate-700/50 text-slate-300',
  pending: 'bg-gold-500/15 text-gold-300',
}
const FILTERS: { id: Game['status'] | 'all'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'won', label: 'Wins' },
  { id: 'lost', label: 'Losses' },
  { id: 'void', label: 'Voided' },
  { id: 'pending', label: 'Pending' },
]

export function HistoryPage() {
  const { runId: activeRunId } = useActiveRun()
  const runs = useRuns()
  const [picked, setPicked] = useState<number | null>(null)
  const [view, setView] = useState<'games' | 'activity'>('games')
  const runId = picked ?? activeRunId

  if (runs.isLoading) return <LoadingState />
  if (!runId) {
    return (
      <EmptyState title="No runs yet">
        <p className="text-sm text-slate-400">Games show up here once you start a run and spin.</p>
        <Link to="/settings" className="btn-primary">
          Start a run
        </Link>
      </EmptyState>
    )
  }
  const run = runs.data?.find((r) => r.id === runId)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">History</h1>
        <select
          className="input max-w-full"
          aria-label="Run"
          value={runId}
          onChange={(e) => setPicked(Number(e.target.value))}
        >
          {runs.data?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name} {r.status === 'ended' ? '(ended)' : ''}
            </option>
          ))}
        </select>
        <div className="inline-flex gap-0.5 rounded-full bg-black/30 p-1 ring-1 ring-gold-700/25 ring-inset" role="group" aria-label="View">
          {(['games', 'activity'] as const).map((v) => (
            <button
              key={v}
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={`rounded-full px-3 py-1 text-sm transition duration-150 ${view === v ? 'bg-gold-700/50 text-gold-100' : 'text-slate-400 hover:text-slate-100'}`}
            >
              {v === 'games' ? 'Games' : 'Pool activity'}
            </button>
          ))}
        </div>
      </div>
      {view === 'games' ? <GameList runId={runId} run={run} /> : <ActivityLog runId={runId} />}
    </div>
  )
}

function GameList({ runId, run }: { runId: number; run: Run | undefined }) {
  const games = useGames(runId)
  const champs = useChampionMap()
  const players = usePlayerMap()
  const undo = useAction((id: number) => api.undo(id))
  const [filter, setFilter] = useState<Game['status'] | 'all'>('all')

  if (games.isLoading) return <LoadingState />
  if (games.error) return <ErrorText error={games.error} />
  const list = games.data ?? []
  if (list.length === 0) return <p className="text-slate-400">No games in this run yet. Spin on the Wheels tab.</p>

  const latest = list[0]
  const count = (status: Game['status'] | 'all') => (status === 'all' ? list.length : list.filter((g) => g.status === status).length)
  const shown = filter === 'all' ? list : list.filter((g) => g.status === filter)

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {FILTERS.filter((f) => f.id === 'all' || count(f.id) > 0).map((f) => (
          <button
            key={f.id}
            aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}
            className={`rounded-full px-3 py-1 text-sm ring-1 ${
              filter === f.id ? 'bg-slate-200 text-slate-950 ring-slate-200' : 'bg-slate-900 ring-slate-700 hover:bg-slate-800'
            }`}
          >
            {f.label} <span className="opacity-60">{count(f.id)}</span>
          </button>
        ))}
      </div>
      <ErrorText error={undo.error} />

      <ul className="flex flex-col gap-2">
        {shown.map((g) => {
          const canUndo = g === latest && g.status !== 'pending' && run?.status === 'active'
          return (
            <li key={g.id} className="card flex flex-col gap-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="flex min-w-36 flex-wrap items-center gap-2 sm:flex-col sm:items-start">
                  <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${STATUS_STYLE[g.status]}`}>
                    {g.status}
                  </span>
                  <span className="text-xs text-slate-400">
                    #{g.id} · {new Date(g.created_at).toLocaleString()}
                  </span>
                  {g.result_source && (
                    <span className="text-xs text-slate-500">{g.result_source === 'auto' ? 'from Riot' : 'recorded by hand'}</span>
                  )}
                  {g.needs_review && <span className="text-xs text-amber-300">needs review</span>}
                  {g.void_reason && <span className="text-xs text-slate-500">{g.void_reason}</span>}
                  {g.tokens_earned.length > 0 && (
                    <span className="text-xs text-gold-300">+{g.tokens_earned.length} revive token(s)</span>
                  )}
                </div>
                <div className="flex flex-1 flex-wrap gap-3">
                  {g.assignments.map((a) => {
                    const cid = a.played_champion_id
                    const eliminated = cid != null && g.eliminated.includes(cid)
                    return (
                      <div key={a.player_id} className="flex items-center gap-2">
                        <ChampionPortrait champion={cid ? champs.get(cid) : undefined} size="sm" dim={eliminated} />
                        <div className="text-xs leading-tight">
                          <div className="font-semibold">{players.get(a.player_id)?.display_name}</div>
                          <div className="text-slate-400">
                            {cid ? champs.get(cid)?.name : 'not marked'}
                            {a.played_option_index != null && ` (#${a.played_option_index + 1})`}
                            {cid && a.played_option_index == null && ' (other)'}
                          </div>
                          {eliminated && <div className="text-red-300">eliminated</div>}
                        </div>
                      </div>
                    )
                  })}
                </div>
                {canUndo && (
                  <button
                    className="btn-secondary"
                    disabled={undo.isPending}
                    onClick={() => confirm(`Undo game ${g.id}? It'll go back to waiting for a result.`) && undo.mutate(g.id)}
                  >
                    Undo result
                  </button>
                )}
              </div>
              {g.match && <MatchSummaryView match={g.match} flagOptions={g.needs_review} />}
            </li>
          )
        })}
      </ul>
    </>
  )
}

function ActivityLog({ runId }: { runId: number }) {
  const events = usePoolEvents(runId)
  const champs = useChampionMap()
  const players = usePlayerMap()
  if (events.isLoading) return <LoadingState />
  if (events.error) return <ErrorText error={events.error} />
  const list = events.data ?? []
  if (list.length === 0) return <p className="text-slate-400">No eliminations or revives in this run yet.</p>

  const name = (cid: string | null) => (cid ? (champs.get(cid)?.name ?? cid) : 'Unknown')
  const who = (pid: number | null) => (pid ? (players.get(pid)?.display_name ?? `Player ${pid}`) : 'someone')
  const describe = (e: PoolEvent) => {
    switch (e.type) {
      case 'eliminate':
        return `${name(e.champion_id)} eliminated, played by ${who(e.player_id)} in game #${e.game_id}`
      case 'revive':
        return `${who(e.player_id)} used a revive token on ${name(e.champion_id)}`
      case 'manual_eliminate':
        return `${name(e.champion_id)} removed by hand`
      case 'manual_revive':
        return `${name(e.champion_id)} brought back by hand`
    }
  }
  const tone: Record<PoolEvent['type'], string> = {
    eliminate: 'bg-red-500',
    manual_eliminate: 'bg-red-500/50',
    revive: 'bg-gold-400',
    manual_revive: 'bg-emerald-500/60',
  }

  return (
    <ul className="card flex flex-col divide-y divide-slate-800 p-0">
      {list.map((e) => (
        <li key={e.id} className={`flex items-center gap-3 px-4 py-2.5 text-sm ${e.undone ? 'opacity-50' : ''}`}>
          <span className={`h-2 w-2 shrink-0 rounded-full ${tone[e.type]}`} />
          <ChampionPortrait champion={e.champion_id ? champs.get(e.champion_id) : undefined} size="xs" />
          <span className={`flex-1 ${e.undone ? 'line-through' : ''}`}>{describe(e)}</span>
          {e.undone && <span className="text-xs text-slate-400">undone</span>}
          <span className="hidden text-xs text-slate-500 sm:inline">{new Date(e.created_at).toLocaleString()}</span>
        </li>
      ))}
    </ul>
  )
}
