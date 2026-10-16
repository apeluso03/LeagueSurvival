import { useEffect, useRef, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useActiveRun, useTeamColors } from '../hooks/queries'
import { usePageTitle } from '../hooks/usePageTitle'
import { setMuted, useMuted } from '../lib/sound'
import { ErrorBoundary } from './ErrorBoundary'
import { LogoMark, SoundOffIcon, SoundOnIcon } from './icons'
import { ModeToggle } from './ModeToggle'
import { UserMenu } from './UserMenu'
import { BackendDownBanner, ResultWatcher, NoChampionsBanner } from './StatusBanners'

const TABS = [
  { to: '/wheels', label: 'Wheels' },
  { to: '/pool', label: 'Pool' },
  { to: '/shop', label: 'Shop' },
  { to: '/stats', label: 'Stats' },
  { to: '/trophies', label: 'Trophies' },
  { to: '/history', label: 'History' },
  { to: '/settings', label: 'Settings' },
]

function BugCell({ label, value, accent = false }: { label: string; value: ReactNode; accent?: boolean }) {
  return (
    <span className="sb-cell">
      <b className={accent ? 'text-gold-300' : 'text-white'}>{value}</b>
      <small>{label}</small>
    </span>
  )
}

/** The run's numbers as a broadcast score bug. */
function RunSummary() {
  const { settings, run } = useActiveRun()
  const r = run.data
  if (!settings.data || run.isLoading) return null
  if (!r) return <span className="text-sm text-slate-400">No active run</span>
  return (
    <div className="score-bug">
      <span className="sb-run hidden lg:flex" title={r.name}>
        {r.name}
        {r.status === 'ended' && <span className="ml-1 text-[10px] text-red-900">ENDED</span>}
      </span>
      <BugCell label="Wins" value={r.win_count} accent />
      <BugCell label="Streak" value={r.current_streak} />
      <BugCell label="Alive" value={`${r.alive_count}/${r.total_count}`} />
      <span data-token-counter className="inline-flex">
        <BugCell label="Tokens" value={r.tokens_available} />
      </span>
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
      className="grid h-8 w-8 place-items-center rounded-sm text-slate-400 ring-1 ring-white/12 transition duration-150 ring-inset hover:text-hex-200 active:scale-90"
    >
      {muted ? <SoundOffIcon width={16} height={16} /> : <SoundOnIcon width={16} height={16} />}
    </button>
  )
}

/** Keeps --header-h in sync with the sticky header, so other sticky bars can sit right under it. */
function useHeaderHeight() {
  const ref = useRef<HTMLElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(() => document.documentElement.style.setProperty('--header-h', `${el.offsetHeight}px`))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return ref
}

export function Layout() {
  const { pathname } = useLocation()
  const headerRef = useHeaderHeight()
  useTeamColors()
  // Tabs set the title here; other pages (player, recap) set their own.
  usePageTitle(TABS.find((t) => t.to === pathname)?.label ?? (pathname === '/' ? '' : null))
  return (
    <div className="flex min-h-dvh flex-col">
      <header ref={headerRef} className="broadcast-header sticky top-0 z-40">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 pt-2.5 pb-2">
          <div className="flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 rounded-full pr-1" title="Home">
              <LogoMark className="h-8 w-8" />
              <span className="font-display hidden text-lg tracking-[0.12em] whitespace-nowrap uppercase sm:inline">
                <span className="text-white">LoL</span> <span className="blue-text">Survival</span>
              </span>
            </Link>
            <ModeToggle />
            <SoundToggle />
          </div>
          <div className="flex items-center gap-3">
            <RunSummary />
            <UserMenu />
          </div>
        </div>
        <nav className="mx-auto max-w-7xl overflow-x-auto px-4">
          <div className="tab-strip">
            {TABS.map((t) => (
              <NavLink key={t.to} to={t.to} end className={({ isActive }) => `tab ${isActive ? 'is-active' : ''}`}>
                {t.label}
              </NavLink>
            ))}
          </div>
        </nav>
      </header>
      <BackendDownBanner />
      <NoChampionsBanner />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-5">
        <ErrorBoundary resetKey={pathname}>
          <div key={pathname} className="page-in">
            <Outlet />
          </div>
        </ErrorBoundary>
      </main>
      <ResultWatcher />
    </div>
  )
}
