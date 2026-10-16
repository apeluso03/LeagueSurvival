import { useQuery } from '@tanstack/react-query'
import { useState, type CSSProperties, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { LowerThird } from '../components/LowerThird'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState } from '../components/ui'
import { useAchievements, useActiveRun, useChampionMap, usePlayers, useRuns } from '../hooks/queries'
import { num, pct } from '../lib/stats'
import { teamColor } from '../lib/teams'
import { TIER_COLORS } from '../lib/tiers'
import type { ShameGame } from '../types'

/** Trophies tab: achievements (with titles) and the Hall of Shame. */
export function TrophiesPage() {
  const [view, setView] = useState<'achievements' | 'shame'>('achievements')
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl text-white">Trophies</h1>
        <div className="inline-flex rounded-sm bg-black/30 p-1 ring-1 ring-white/10 ring-inset" role="group" aria-label="View">
          {(
            [
              ['achievements', 'Achievements'],
              ['shame', 'Hall of Shame'],
            ] as const
          ).map(([v, label]) => (
            <button
              key={v}
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={`rounded-sm px-3 py-1 text-sm transition duration-150 ${
                view === v ? (v === 'shame' ? 'bg-red-700/70 text-white' : 'bg-hex-500/60 text-white') : 'text-slate-400 hover:text-slate-100'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <Link to="/wrapped" className="btn-gold ml-auto">
          Monthly Wrapped
        </Link>
      </div>
      {view === 'achievements' ? <Achievements /> : <HallOfShame />}
    </div>
  )
}

function Achievements() {
  const report = useAchievements()
  const players = usePlayers()
  const [who, setWho] = useState<number | null>(null)
  if (report.isLoading) return <LoadingState />
  if (!report.data) return <ErrorText error={report.error} />
  const r = report.data
  const list = players.data ?? []
  const holders = (id: string) =>
    list
      .map((p) => ({ player: p, unlock: r.players[String(p.id)]?.find((u) => u.id === id) }))
      .filter((x) => x.unlock)
      .sort((a, b) => a.unlock!.at.localeCompare(b.unlock!.at))
  const mine = who != null ? new Set((r.players[String(who)] ?? []).map((u) => u.id)) : null
  const total = r.catalog.length
  const unlockedAny = r.catalog.filter((a) => holders(a.id).length > 0).length
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-400">
          {mine ? `${mine.size} of ${total} unlocked` : `${unlockedAny} of ${total} unlocked by someone`}
        </span>
        <div className="ml-auto flex flex-wrap gap-1.5">
          <button className={`team-chip ${who == null ? 'is-on' : ''}`} style={{ ['--team' as string]: '#636d80' }} onClick={() => setWho(null)}>
            Everyone
          </button>
          {list.map((p) => (
            <button
              key={p.id}
              className={`team-chip ${who === p.id ? 'is-on' : ''}`}
              style={{ ['--team' as string]: teamColor(p.id) }}
              onClick={() => setWho(who === p.id ? null : p.id)}
            >
              {p.display_name}
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {r.catalog.map((a) => {
          const got = holders(a.id)
          const locked = mine ? !mine.has(a.id) : got.length === 0
          return (
            <div
              key={a.id}
              className={`trophy-card flex gap-3 p-4 ${locked ? 'is-locked' : ''}`}
              style={{ '--tier': TIER_COLORS[a.tier] } as CSSProperties}
            >
              <span className="trophy-icon" aria-hidden>
                {a.icon}
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-display text-lg tracking-wide text-white uppercase">{a.name}</span>
                  <span className="text-[10px] font-bold tracking-[0.14em] uppercase" style={{ color: TIER_COLORS[a.tier] }}>
                    {a.tier}
                  </span>
                </div>
                <span className="text-sm text-slate-300">{a.description}</span>
                <span className="text-[11px] text-slate-500">
                  Title: <i className="text-slate-300">“{a.title}”</i> · {pct(r.rarity[a.id] ?? 0)} of players
                </span>
                {got.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {got.map(({ player, unlock }) => (
                      <span key={player.id} title={`Unlocked ${new Date(unlock!.at).toLocaleDateString()}${unlock!.game_id ? ` in game ${unlock!.game_id}` : ''}`}>
                        <LowerThird playerId={player.id} size="sm" />
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}

function ShameSection({ title, children, empty }: { title: string; children: ReactNode; empty: boolean }) {
  return (
    <section className="shame-panel flex flex-col gap-3 p-4">
      <h2 className="postgame-title shame-title">{title}</h2>
      {empty ? <p className="text-sm text-slate-500">Nothing shameful here yet. Give it time.</p> : children}
    </section>
  )
}

function GameRow({ g, highlight }: { g: ShameGame; highlight: 'kda' | 'deaths' | 'duration' }) {
  const champs = useChampionMap()
  const champ = g.champion_id ? champs.get(g.champion_id) : undefined
  const mins = g.duration ? `${Math.floor(g.duration / 60)}:${String(g.duration % 60).padStart(2, '0')}` : '—'
  return (
    <li className="flex items-center gap-3 text-sm">
      <ChampionPortrait champion={champ} size="sm" dim />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <LowerThird playerId={g.player_id} size="sm" sub={champ?.name} />
        <span className="text-[11px] text-slate-500">
          Game {g.game_id} · {new Date(g.at).toLocaleDateString()} · {g.won ? 'won anyway' : 'lost'}
        </span>
      </div>
      <span className="font-display text-lg text-red-300 tabular-nums">
        {highlight === 'duration' ? mins : `${g.kills}/${g.deaths}/${g.assists}`}
      </span>
      {highlight === 'kda' && <span className="w-12 text-right text-xs text-slate-400">{num(g.kda, 2)} KDA</span>}
    </li>
  )
}

function HallOfShame() {
  const { runId: activeRunId } = useActiveRun()
  const runs = useRuns()
  const champs = useChampionMap()
  const [picked, setPicked] = useState<number | null | undefined>(undefined)
  const runId = picked === undefined ? activeRunId : picked
  const shame = useQuery({ queryKey: ['shame', runId], queryFn: () => api.shame(runId) })
  if (shame.isLoading) return <LoadingState />
  if (!shame.data) return <ErrorText error={shame.error} />
  const s = shame.data
  const maxDeaths = Math.max(...s.feeders.map((f) => f.avg_deaths), 1)
  const nothing =
    !s.worst_games.length && !s.cursed_champions.length && !s.reapers.length && !s.wasted_items.length && !s.feeders.length
  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <span className="broadcast-tag" style={{ ['--tag' as string]: '#c8102e' }}>
          Hall of Shame
        </span>
        <span className="text-sm text-slate-400">The moments everyone would rather forget. Forever.</span>
        <select
          className="input ml-auto"
          aria-label="Run"
          value={runId ?? ''}
          onChange={(e) => setPicked(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">All runs</option>
          {runs.data?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </div>
      {nothing ? (
        <EmptyState title="A clean record (for now)">
          <p className="text-sm text-slate-400">Play some games. Riot data (KDA) makes this page much meaner.</p>
        </EmptyState>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <ShameSection title="The inting reel" empty={!s.worst_games.length}>
            <ol className="flex flex-col gap-2.5">
              {s.worst_games.map((g) => (
                <GameRow key={`${g.game_id}-${g.player_id}`} g={g} highlight="kda" />
              ))}
            </ol>
          </ShameSection>
          <div className="flex flex-col gap-4">
            <ShameSection title="Most deaths in one game" empty={!s.most_deaths.length}>
              <ol className="flex flex-col gap-2.5">
                {s.most_deaths.map((g) => (
                  <GameRow key={`${g.game_id}-${g.player_id}`} g={g} highlight="deaths" />
                ))}
              </ol>
            </ShameSection>
            <ShameSection title="Fastest losses" empty={!s.fastest_losses.length}>
              <ol className="flex flex-col gap-2.5">
                {s.fastest_losses.map((g) => (
                  <GameRow key={`${g.game_id}-${g.player_id}`} g={g} highlight="duration" />
                ))}
              </ol>
            </ShameSection>
          </div>
          <ShameSection title="Cursed champions" empty={!s.cursed_champions.length}>
            <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
              {s.cursed_champions.map((c) => (
                <div key={c.champion_id} className="flex flex-col items-center gap-1 text-center" title={champs.get(c.champion_id)?.name}>
                  <ChampionPortrait champion={champs.get(c.champion_id)} size="lg" dim className="rounded-sm" />
                  <span className="text-xs text-red-300 tabular-nums">
                    {c.wins}–{c.games - c.wins}
                  </span>
                </div>
              ))}
            </div>
          </ShameSection>
          <ShameSection title="Feeders (average deaths)" empty={!s.feeders.length}>
            <div className="flex flex-col gap-2">
              {s.feeders.map((f) => (
                <div key={f.player_id} className="grid grid-cols-[6rem_1fr_3.5rem] items-center gap-2 text-sm">
                  <LowerThird playerId={f.player_id} size="sm" />
                  <span className="h-2.5 bg-white/[0.06]">
                    <span
                      className="stat-bar block h-full"
                      style={{ width: `${(f.avg_deaths / maxDeaths) * 100}%`, ['--team' as string]: teamColor(f.player_id) }}
                    />
                  </span>
                  <span className="text-right text-red-300 tabular-nums">{num(f.avg_deaths, 1)}</span>
                </div>
              ))}
            </div>
          </ShameSection>
          <ShameSection title="Grim reapers (champs lost)" empty={!s.reapers.length}>
            <ol className="flex flex-col gap-1.5">
              {s.reapers.map((r, i) => (
                <li key={r.player_id} className="flex items-center gap-3 text-sm">
                  <span className="w-5 text-slate-500">{i + 1}</span>
                  <LowerThird playerId={r.player_id} size="sm" />
                  <span className="ml-auto text-red-300 tabular-nums">💀 {r.champions_lost}</span>
                </li>
              ))}
            </ol>
          </ShameSection>
          <ShameSection title="Rerolled and lost anyway" empty={!s.wasted_items.length}>
            <ol className="flex flex-col gap-1.5">
              {s.wasted_items.map((w) => (
                <li key={w.player_id} className="flex items-center gap-3 text-sm">
                  <LowerThird playerId={w.player_id} size="sm" />
                  <span className="ml-auto text-slate-300">
                    {w.items} item{w.items === 1 ? '' : 's'} · <b className="text-gold-300">{w.gold.toLocaleString()} gold</b> down the drain
                  </span>
                </li>
              ))}
            </ol>
          </ShameSection>
        </div>
      )}
    </>
  )
}
