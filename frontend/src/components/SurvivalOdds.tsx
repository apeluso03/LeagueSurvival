import { useMemo } from 'react'
import { oddsTargets, simulateRun } from '../lib/odds'
import { pct } from '../lib/stats'
import type { Run } from '../types'

/** Chances of reaching the next few win goals, from 2,000 simulated futures of this run. */
export function SurvivalOdds({ run, players }: { run: Run; players: number }) {
  const targets = oddsTargets(run.win_count)
  const odds = useMemo(
    () =>
      simulateRun({
        wins: run.win_count,
        games: run.games_played,
        alive: run.alive_count,
        total: run.total_count,
        tokens: run.tokens_available,
        streak: run.current_streak,
        players,
        targets,
      }),
    // targets follow from win_count
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [run.win_count, run.games_played, run.alive_count, run.total_count, run.tokens_available, run.current_streak, players],
  )
  const tone = (chance: number) => (chance >= 0.6 ? 'text-hex-200' : chance >= 0.3 ? 'text-gold-300' : 'text-red-300')
  return (
    <div className="odds-panel flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3">
      <span className="broadcast-tag" style={{ ['--tag' as string]: 'var(--color-hex-500)' }}>
        Survival odds
      </span>
      {odds.reach.map(({ target, chance }) => (
        <div key={target} className="flex items-baseline gap-1.5">
          <span className={`font-display text-2xl ${tone(chance)}`}>{chance > 0 && chance < 0.01 ? '<1%' : pct(chance)}</span>
          <span className="text-xs text-slate-400">to {target} wins</span>
        </div>
      ))}
      <span className="text-sm text-slate-400">
        Most likely finish: <b className="text-white">{odds.medianWins}</b> wins · lucky run: <b className="text-white">{odds.p90Wins}</b>
      </span>
      <span className="ml-auto text-[11px] text-slate-500" title="Win rate pulled toward 50% while there are few games">
        {pct(odds.winRate)} win rate · {players} players · 2,000 simulated runs
      </span>
    </div>
  )
}
