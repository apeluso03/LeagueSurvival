import { NavLink, Outlet } from 'react-router-dom'
import { useActiveRun } from '../hooks/queries'
import { ModeToggle } from './ModeToggle'
import { Stat } from './ui'

const TABS = [
  { to: '/', label: 'Wheels' },
  { to: '/pool', label: 'Pool' },
  { to: '/stats', label: 'Stats' },
  { to: '/history', label: 'History' },
  { to: '/settings', label: 'Settings' },
]

function RunSummary() {
  const { run } = useActiveRun()
  const r = run.data
  if (!r) return <span className="text-sm text-slate-400">No active run</span>
  return (
    <div className="flex items-center gap-5">
      <span className="hidden max-w-40 truncate text-sm font-semibold text-slate-300 md:block" title={r.name}>
        {r.name}
        {r.status === 'ended' && <span className="ml-1 text-xs text-red-400">(ended)</span>}
      </span>
      <Stat label="Wins" value={r.win_count} accent />
      <Stat label="Streak" value={r.current_streak} />
      <Stat label="Alive" value={`${r.alive_count}/${r.total_count}`} />
      <Stat label="Tokens" value={r.tokens_available} />
    </div>
  )
}

export function Layout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-2">
          <div className="flex items-center gap-3">
            <span className="text-lg font-black tracking-tight text-gold-400">LoL Survival</span>
            <ModeToggle />
          </div>
          <RunSummary />
        </div>
        <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-4">
          {TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end
              className={({ isActive }) =>
                `border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap ${
                  isActive ? 'border-gold-500 text-gold-300' : 'border-transparent text-slate-400 hover:text-slate-200'
                }`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
