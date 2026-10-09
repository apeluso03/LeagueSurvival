import { useChampionMap, usePlayerMap } from '../hooks/queries'
import { formatDuration, queueName } from '../lib/queues'
import type { MatchSummary } from '../types'
import { ChampionPortrait } from './ui'

/** The tracked players' line from a Riot match: champion, K/D/A, and whether it was one of their options. */
export function MatchSummaryView({ match, flagOptions = false }: { match: MatchSummary; flagOptions?: boolean }) {
  const champs = useChampionMap()
  const players = usePlayerMap()
  const teams = new Set(match.players.map((p) => p.team_id))
  const win = match.players.length > 0 && match.players.every((p) => p.win)

  return (
    <div className="flex flex-col gap-2 rounded-lg bg-slate-950/60 p-3 text-sm">
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-400">
        <span className={win ? 'text-emerald-300' : 'text-red-300'}>{win ? 'Win' : 'Loss'}</span>
        <span>{queueName(match.queue_id)}</span>
        <span>{formatDuration(match.game_duration)}</span>
        {match.early_surrender && <span>Early surrender</span>}
        {teams.size > 1 && <span className="text-amber-300">Different teams</span>}
        {match.game_start && <span>{new Date(match.game_start).toLocaleString()}</span>}
        <span className="text-slate-500">{match.match_id}</span>
      </div>
      <div className="flex flex-wrap gap-4">
        {match.players.map((p) => (
          <div key={p.player_id} className="flex items-center gap-2">
            <ChampionPortrait
              champion={p.champion_id ? champs.get(p.champion_id) : undefined}
              size="sm"
              className={flagOptions && !p.in_options ? 'ring-2 ring-amber-400' : ''}
            />
            <div className="text-xs leading-tight">
              <div className="font-semibold">{players.get(p.player_id)?.display_name}</div>
              <div className="text-slate-300">
                {(p.champion_id && champs.get(p.champion_id)?.name) ?? 'Unknown'}{' '}
                <span className="tabular-nums text-slate-400">
                  {p.kills}/{p.deaths}/{p.assists}
                </span>
              </div>
              {flagOptions && !p.in_options && <div className="text-amber-300">not one of their options</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
