import { useState } from 'react'
import { api } from '../api/client'
import { ChampionPortrait, EmptyState, ErrorText, Stat } from '../components/ui'
import {
  useAction,
  useActiveRun,
  useChampionMap,
  usePlayerMap,
  usePlayerStats,
  useRiotStatus,
  useRuns,
} from '../hooks/queries'
import { num, pct, sortRows } from '../lib/stats'
import type { PlayerStats, Run } from '../types'

type Column = {
  label: string
  title?: string
  value: (s: PlayerStats) => number | string | null
  show: (s: PlayerStats) => string
}

export function StatsPage() {
  const { runId: activeRunId } = useActiveRun()
  const runs = useRuns()
  const riot = useRiotStatus()
  const sync = useAction(api.sync)
  const [challengeOnly, setChallengeOnly] = useState(true)
  // undefined = follow the active run; null = all runs
  const [pickedRun, setPickedRun] = useState<number | null | undefined>(undefined)
  const runId = pickedRun === undefined ? activeRunId : pickedRun
  const stats = usePlayerStats(runId, challengeOnly)
  const run = runs.data?.find((r) => r.id === runId)

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">Stats</h1>
        <div className="flex overflow-hidden rounded-md ring-1 ring-slate-700" role="group" aria-label="Games to include">
          {[
            [true, 'Challenge only'],
            [false, 'All tracked games'],
          ].map(([value, label]) => (
            <button
              key={String(value)}
              onClick={() => setChallengeOnly(value as boolean)}
              aria-pressed={challengeOnly === value}
              className={`px-3 py-1.5 text-sm ${challengeOnly === value ? 'bg-gold-500 text-slate-950' : 'bg-slate-900 hover:bg-slate-800'}`}
            >
              {label as string}
            </button>
          ))}
        </div>
        <select
          className="input"
          aria-label="Run"
          value={runId ?? ''}
          onChange={(e) => setPickedRun(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">All runs</option>
          {runs.data?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name} {r.status === 'ended' ? '(ended)' : ''}
            </option>
          ))}
        </select>
        {riot.data?.key_set && (
          <button className="btn-secondary ml-auto" disabled={sync.isPending} onClick={() => sync.mutate(undefined)}>
            {sync.isPending ? 'Syncing...' : 'Sync matches'}
          </button>
        )}
      </div>
      <ErrorText error={sync.error ?? stats.error} />
      {riot.data && !riot.data.key_set && (
        <p className="text-sm text-slate-400">
          KDA, KP and per-minute stats need Riot match data. Add a Riot API key (see Settings) and link players' Riot IDs.
          Win/loss stats from challenge games work without it.
        </p>
      )}

      {run && <RunSummary run={run} />}

      {stats.data && stats.data.length === 0 && <EmptyState title="No players yet" />}
      {stats.data && stats.data.length > 0 && (
        <>
          <Leaderboard rows={stats.data} />
          <div className="grid gap-4 md:grid-cols-2">
            {stats.data.map((s) => (
              <PlayerCard key={s.player_id} stats={s} challengeOnly={challengeOnly} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function RunSummary({ run }: { run: Run }) {
  return (
    <div className="card flex flex-wrap justify-around gap-6">
      <Stat label="Total wins" value={run.win_count} accent />
      <Stat label="Best streak" value={run.best_streak} />
      <Stat label="Games played" value={run.games_played} />
      <Stat label="Eliminated" value={run.total_count - run.alive_count} />
      <Stat label="Champions left" value={run.alive_count} />
    </div>
  )
}

function Leaderboard({ rows }: { rows: PlayerStats[] }) {
  const players = usePlayerMap()
  const name = (s: PlayerStats) => players.get(s.player_id)?.display_name ?? `#${s.player_id}`
  const columns: Column[] = [
    { label: 'Player', value: name, show: name },
    { label: 'Games', value: (s) => s.games, show: (s) => String(s.games) },
    { label: 'W', value: (s) => s.wins, show: (s) => String(s.wins) },
    { label: 'L', value: (s) => s.losses, show: (s) => String(s.losses) },
    { label: 'Win %', value: (s) => s.win_rate, show: (s) => pct(s.win_rate) },
    { label: 'KDA', title: '(Kills + Assists) / Deaths', value: (s) => s.kda, show: (s) => num(s.kda, 2) },
    {
      label: 'K / D / A',
      title: 'Average kills / deaths / assists',
      value: (s) => s.avg_kills,
      show: (s) => (s.avg_kills == null ? '—' : `${num(s.avg_kills)} / ${num(s.avg_deaths)} / ${num(s.avg_assists)}`),
    },
    { label: 'KP', title: 'Kill participation', value: (s) => s.kill_participation, show: (s) => pct(s.kill_participation) },
    { label: 'CS/m', value: (s) => s.cs_per_min, show: (s) => num(s.cs_per_min) },
    { label: 'DPM', title: 'Damage to champions per minute', value: (s) => s.damage_per_min, show: (s) => num(s.damage_per_min, 0) },
    { label: 'VS/m', title: 'Vision score per minute', value: (s) => s.vision_per_min, show: (s) => num(s.vision_per_min, 2) },
    {
      label: 'Elims',
      title: 'Champions eliminated in challenge losses',
      value: (s) => s.eliminated_champions.length,
      show: (s) => String(s.eliminated_champions.length),
    },
  ]
  const [sort, setSort] = useState<{ col: number; desc: boolean }>({ col: 4, desc: true })
  const sorted = sortRows(rows, columns[sort.col].value, sort.desc)

  return (
    <div className="card overflow-x-auto p-0">
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-slate-800 text-left text-xs uppercase tracking-wide text-slate-400">
            {columns.map((c, i) => (
              <th key={c.label} className="px-3 py-2 font-medium">
                <button
                  title={c.title}
                  className={`hover:text-slate-100 ${sort.col === i ? 'text-gold-300' : ''}`}
                  onClick={() => setSort((s) => ({ col: i, desc: s.col === i ? !s.desc : i !== 0 }))}
                >
                  {c.label}
                  {sort.col === i && (sort.desc ? ' ▼' : ' ▲')}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => (
            <tr key={s.player_id} className="border-b border-slate-800/60 last:border-0">
              {columns.map((c, i) => (
                <td key={c.label} className={`px-3 py-2 ${i === 0 ? 'font-semibold' : 'tabular-nums'}`}>
                  {c.show(s)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PlayerCard({ stats: s, challengeOnly }: { stats: PlayerStats; challengeOnly: boolean }) {
  const players = usePlayerMap()
  const champs = useChampionMap()
  const player = players.get(s.player_id)

  return (
    <div className="card flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">{player?.display_name}</h2>
        <span className="text-sm text-slate-400">
          {s.wins}W {s.losses}L · {pct(s.win_rate)}
        </span>
      </div>

      {s.games === 0 ? (
        <p className="text-sm text-slate-400">
          {challengeOnly ? 'No challenge games yet.' : 'No games yet.'}
        </p>
      ) : s.detailed_games === 0 ? (
        <p className="text-sm text-slate-400">
          No Riot match data yet, so only wins and losses are shown.{' '}
          {player?.puuid ? 'Sync matches to pull in KDA and more.' : 'Link their Riot ID in Settings to get KDA and more.'}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
            <Stat label="KDA" value={num(s.kda, 2)} accent />
            <Stat label="K/D/A" value={s.avg_kills == null ? '—' : `${num(s.avg_kills)}/${num(s.avg_deaths)}/${num(s.avg_assists)}`} />
            <Stat label="KP" value={pct(s.kill_participation)} />
            <Stat label="CS/m" value={num(s.cs_per_min)} />
            <Stat label="DPM" value={num(s.damage_per_min, 0)} />
            <Stat label="VS/m" value={num(s.vision_per_min, 2)} />
          </div>
          {s.detailed_games < s.games && (
            <p className="text-xs text-slate-500">
              Riot stats from {s.detailed_games} of {s.games} games. The rest were recorded by hand.
            </p>
          )}
        </>
      )}

      <div className="flex flex-col gap-2">
        <h3 className="text-xs uppercase tracking-wide text-slate-400">Best champions (2+ games)</h3>
        {s.best_champions.length === 0 ? (
          <p className="text-sm text-slate-500">Not enough games on any champion yet.</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {s.best_champions.slice(0, 5).map((c) => (
              <li key={c.champion_id} className="flex items-center gap-2 text-sm">
                <ChampionPortrait champion={champs.get(c.champion_id)} size="sm" />
                <span className="flex-1 font-medium">{champs.get(c.champion_id)?.name ?? c.champion_id}</span>
                <span className="tabular-nums text-slate-300">
                  {c.wins}/{c.games} · {pct(c.win_rate)}
                </span>
                <span className="w-16 text-right tabular-nums text-slate-400">{c.kda == null ? '' : `${num(c.kda, 2)} KDA`}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {s.eliminated_champions.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="text-xs uppercase tracking-wide text-slate-400">
            Eliminated in challenge losses ({s.eliminated_champions.length})
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {s.eliminated_champions.map((cid, i) => (
              <ChampionPortrait key={`${cid}-${i}`} champion={champs.get(cid)} size="sm" dim />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
