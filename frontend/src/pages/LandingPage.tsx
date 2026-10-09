import type { ComponentType, SVGProps } from 'react'
import { Link } from 'react-router-dom'
import { ChartIcon, ClockIcon, GearIcon, LogoMark, PoolIcon, WheelIcon } from '../components/icons'
import { SoundToggle } from '../components/Layout'
import { ModeToggle } from '../components/ModeToggle'
import { BackendDownBanner, NoChampionsBanner } from '../components/StatusBanners'
import { Stat } from '../components/ui'
import { useActiveRun, useChampions } from '../hooks/queries'
import { usePageTitle } from '../hooks/usePageTitle'

type Tile = {
  to: string
  title: string
  blurb: string
  Icon: ComponentType<SVGProps<SVGSVGElement>>
}

const TILES: Tile[] = [
  { to: '/pool', title: 'Champion Pool', blurb: "See who's still alive", Icon: PoolIcon },
  { to: '/stats', title: 'Stats', blurb: "How everyone's doing", Icon: ChartIcon },
  { to: '/history', title: 'History', blurb: "Every game you've played", Icon: ClockIcon },
  { to: '/settings', title: 'Settings', blurb: 'Players, runs and your Riot key', Icon: GearIcon },
]

/** Title page (SPEC 17.2). Sign-in is reserved for the online lobby. */
export function LandingPage() {
  usePageTitle('')
  const { run } = useActiveRun()
  const champions = useChampions()
  const r = run.data
  const patch = champions.data?.[0]?.ddragon_version

  return (
    <div className="relative flex min-h-dvh flex-col overflow-hidden">
      <BackendDownBanner />
      <NoChampionsBanner />

      {/* hextech rings behind the logo */}
      <div aria-hidden className="pointer-events-none absolute top-[-12rem] left-1/2 -translate-x-1/2">
        <div className="landing-ring h-[44rem] w-[44rem] rounded-full ring-1 ring-hex-300/15" />
        <div className="landing-ring-slow absolute inset-16 rounded-full ring-1 ring-gold-500/15" />
        <div className="absolute inset-40 rounded-full bg-hex-300/[0.06] blur-3xl" />
      </div>

      <div className="relative z-10 flex items-center justify-end gap-2 px-4 pt-4">
        <ModeToggle />
        <SoundToggle />
        <button
          disabled
          title="Coming with online play"
          className="btn-secondary px-3 py-1.5 text-xs"
        >
          Sign in · soon
        </button>
      </div>

      <main className="page-in relative z-10 mx-auto flex w-full max-w-4xl flex-1 flex-col items-center px-4 pt-6 pb-12 text-center sm:pt-10">
        <LogoMark className="h-24 w-24 drop-shadow-[0_0_30px_rgb(10_200_185/0.25)] sm:h-28 sm:w-28" />
        <h1 className="gold-text mt-5 text-4xl font-black tracking-[0.12em] sm:text-6xl">LEAGUE SURVIVAL</h1>
        <p className="mt-3 max-w-md text-sm text-slate-300 sm:text-base">
          Spin for your champs. Win and you keep them. Lose and they're gone.
        </p>

        <div className="mt-8 flex w-full max-w-xl flex-col items-center gap-4">
          {r ? (
            <div className="glass flex w-full flex-wrap items-center justify-around gap-4 rounded-3xl px-5 py-4">
              <div className="text-left">
                <div className="text-[10px] tracking-[0.15em] text-slate-400 uppercase">
                  {r.status === 'ended' ? 'Last run' : 'Current run'}
                </div>
                <div className="max-w-44 truncate font-semibold text-gold-100">{r.name}</div>
              </div>
              <Stat label="Wins" value={r.win_count} accent />
              <Stat label="Streak" value={r.current_streak} />
              <Stat label="Alive" value={`${r.alive_count}/${r.total_count}`} />
              <Stat label="Tokens" value={r.tokens_available} />
            </div>
          ) : (
            run.isSuccess && (
              <p className="glass rounded-3xl px-5 py-3 text-sm text-slate-300">
                No run going yet. Head to Settings to add players and start one.
              </p>
            )
          )}

          <Link
            to="/wheels"
            className="btn-primary group w-full max-w-sm py-3.5 text-base tracking-[0.15em] uppercase"
          >
            <WheelIcon className="h-5 w-5 transition-transform duration-500 group-hover:rotate-180" />
            {r?.pending_game_id ? 'Back to the game' : 'Spin the wheels'}
          </Link>
        </div>

        <nav className="mt-10 grid w-full grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Sections">
          {TILES.map(({ to, title, blurb, Icon }) => (
            <Link
              key={to}
              to={to}
              className="glass group flex flex-col items-center gap-2 rounded-3xl px-3 py-5 transition duration-200 ease-(--ease-snap) hover:-translate-y-0.5 hover:ring-gold-500/50 active:scale-[0.97]"
            >
              <span className="grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-b from-hex-600/40 to-hex-800/60 text-hex-200 ring-1 ring-hex-300/25 ring-inset transition group-hover:text-hex-100">
                <Icon className="h-5 w-5" />
              </span>
              <span className="font-display text-sm font-bold text-gold-100">{title}</span>
              <span className="text-xs leading-snug text-slate-400">{blurb}</span>
            </Link>
          ))}
        </nav>
      </main>

      <footer className="relative z-10 pb-5 text-center text-[11px] text-slate-500">
        {patch && <>Champion data from patch {patch} · </>}Not affiliated with Riot Games
      </footer>
    </div>
  )
}
