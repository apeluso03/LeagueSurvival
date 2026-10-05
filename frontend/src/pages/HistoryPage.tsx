import { useState } from 'react'
import { api } from '../api/client'
import { ChampionPortrait, EmptyState, ErrorText } from '../components/ui'
import { useAction, useActiveRun, useChampionMap, useGames, usePlayerMap, useRuns } from '../hooks/queries'
import type { Game } from '../types'

const STATUS_STYLE: Record<Game['status'], string> = {
  won: 'bg-emerald-500/15 text-emerald-300',
  lost: 'bg-red-500/15 text-red-300',
  void: 'bg-slate-700/50 text-slate-300',
  pending: 'bg-gold-500/15 text-gold-300',
}

export function HistoryPage() {
  const { runId: activeRunId } = useActiveRun()
  const runs = useRuns()
  const [picked, setPicked] = useState<number | null>(null)
  const runId = picked ?? activeRunId
  const games = useGames(runId)
  const champs = useChampionMap()
  const players = usePlayerMap()
  const undo = useAction((id: number) => api.undo(id))

  if (!runId) return <EmptyState title="No runs yet" />
  const list = games.data ?? []
  const latest = list[0]
  const run = runs.data?.find((r) => r.id === runId)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">History</h1>
        <select className="input" value={runId} onChange={(e) => setPicked(Number(e.target.value))}>
          {runs.data?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name} {r.status === 'ended' ? '(ended)' : ''}
            </option>
          ))}
        </select>
      </div>
      <ErrorText error={undo.error} />
      {games.isSuccess && list.length === 0 && <p className="text-slate-400">No games in this run yet.</p>}

      <ul className="flex flex-col gap-2">
        {list.map((g) => {
          const canUndo = g === latest && g.status !== 'pending' && run?.status === 'active'
          return (
            <li key={g.id} className="card flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="flex min-w-36 items-center gap-2 sm:flex-col sm:items-start">
                <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${STATUS_STYLE[g.status]}`}>
                  {g.status}
                </span>
                <span className="text-xs text-slate-400">
                  #{g.id} · {new Date(g.created_at).toLocaleString()}
                </span>
                {g.result_source && <span className="text-xs text-slate-500">{g.result_source}</span>}
                {g.void_reason && <span className="text-xs text-slate-500">{g.void_reason}</span>}
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
                      </div>
                    </div>
                  )
                })}
              </div>
              {g.riot_match_id && <span className="text-xs text-slate-400">{g.riot_match_id}</span>}
              {canUndo && (
                <button className="btn-secondary" disabled={undo.isPending} onClick={() => undo.mutate(g.id)}>
                  Undo result
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
