import { EmptyState, Stat } from '../components/ui'
import { useActiveRun } from '../hooks/queries'

/** Run summary for now. Per-player Riot stats (KDA, KP, CS/min...) arrive with Riot linking (M3). */
export function StatsPage() {
  const { run } = useActiveRun()
  const r = run.data
  if (!r) return <EmptyState title="No active run" />
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-bold">{r.name}</h1>
      <div className="card flex flex-wrap justify-around gap-6">
        <Stat label="Total wins" value={r.win_count} accent />
        <Stat label="Best streak" value={r.best_streak} />
        <Stat label="Games played" value={r.games_played} />
        <Stat label="Eliminated" value={r.total_count - r.alive_count} />
        <Stat label="Champions left" value={r.alive_count} />
      </div>
      <p className="text-sm text-slate-400">
        Player stats (KDA, kill participation, CS and damage per minute, best champions) will appear here once Riot
        match import is set up.
      </p>
    </div>
  )
}
