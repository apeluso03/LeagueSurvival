import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useActiveRun } from '../hooks/queries'
import { usePageTitle } from '../hooks/usePageTitle'
import { setMuted, useMuted } from '../lib/sound'
import { ErrorBoundary } from './ErrorBoundary'
import { LogoMark, SoundOffIcon, SoundOnIcon } from './icons'
import { ModeToggle } from './ModeToggle'
import { BackendDownBanner, BackgroundResultToast, NoChampionsBanner } from './StatusBanners'
import { Stat } from './ui'

const TABS = [
  { to: '/wheels', label: 'Wheels' },
  { to: '/pool', label: 'Pool' },
  { to: '/stats', label: 'Stats' },
  { to: '/history', label: 'History' },
  { to: '/settings', label: 'Settings' },
]

function RunSummary() {
  const { settings, run } = useActiveRun()
  const r = run.data
  if (!settings.data || run.isLoading) return null
  if (!r) return <span className="text-sm text-slate-400">No active run</span>
  return (
    <div className="flex items-center gap-4 sm:gap-5">
      <span className="hidden max-w-44 truncate text-sm font-semibold text-slate-300 lg:block" title={r.name}>
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

export function SoundToggle() {
  const muted = useMuted()
  return (
    <button
      onClick={() => setMuted(!muted)}
      aria-pressed={!muted}
      aria-label={muted ? 'Sound off' : 'Sound on'}
      title={muted ? 'Spin sounds are off' : 'Spin sounds are on'}
      className="grid h-8 w-8 place-items-center rounded-full text-slate-400 ring-1 ring-gold-700/40 transition duration-150 ring-inset hover:text-gold-200 active:scale-90"
    >
      {muted ? <SoundOffIcon width={16} height={16} /> : <SoundOnIcon width={16} height={16} />}
    </button>
  )
}

export function Layout() {
  const { pathname } = useLocation()
  usePageTitle(TABS.find((t) => t.to === pathname)?.label ?? '')
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-40 border-b border-gold-700/25 bg-[#020b16]/95">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 pt-2.5 pb-2">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 rounded-full pr-1" title="Home">
              <LogoMark className="h-8 w-8" />
              <span className="font-display gold-text hidden text-lg font-bold tracking-wider whitespace-nowrap sm:inline">LoL Survival</span>
            </Link>
            <ModeToggle />
            <SoundToggle />
          </div>
          <RunSummary />
        </div>
        <nav className="mx-auto max-w-6xl overflow-x-auto px-4 pb-2.5">
          <div className="inline-flex gap-1 rounded-full bg-black/30 p-1 ring-1 ring-gold-700/25 ring-inset">
            {TABS.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end
                className={({ isActive }) =>
                  `rounded-full px-3.5 py-1.5 text-sm font-medium whitespace-nowrap transition duration-150 ${
                    isActive
                      ? 'bg-gradient-to-b from-gold-700/60 to-gold-800/60 text-gold-100 shadow-[0_0_0_1px_rgb(200_170_110/0.45)_inset]'
                      : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'
                  }`
                }
              >
                {t.label}
              </NavLink>
            ))}
          </div>
        </nav>
      </header>
      <BackendDownBanner />
      <NoChampionsBanner />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <ErrorBoundary resetKey={pathname}>
          <div key={pathname} className="page-in">
            <Outlet />
          </div>
        </ErrorBoundary>
      </main>
      <BackgroundResultToast />
    </div>
  )
}
