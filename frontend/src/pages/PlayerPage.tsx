import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { GoldBadge } from '../components/Gold'
import { SkullIcon } from '../components/icons'
import { ItemArt } from '../components/ItemArt'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState, Stat } from '../components/ui'
import { useAchievements, useAction, useActiveRun, useChampionMap, usePlayerMap, useRuns } from '../hooks/queries'
import { useAccess } from '../hooks/useAuth'
import { usePageTitle } from '../hooks/usePageTitle'
import { loadingUrl, splashUrl } from '../lib/champions'
import { ITEM_META, ITEM_ORDER } from '../lib/items'
import { num, pct } from '../lib/stats'
import { teamColor } from '../lib/teams'
import type { PlayerProfile } from '../types'

function Section({ title, children, right }: { title: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="card flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-xs font-semibold tracking-[0.14em] text-slate-400 uppercase">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  )
}

/** A player's page: how they're doing, what they play, their recent games and gold. */
export function PlayerPage() {
  const id = Number(useParams().id)
  const { runId: activeRunId } = useActiveRun()
  const runs = useRuns()
  // undefined = follow the active run; null = every run
  const [pickedRun, setPickedRun] = useState<number | null | undefined>(undefined)
  const runId = pickedRun === undefined ? activeRunId : pickedRun
  const profile = useQuery({
    queryKey: ['profile', id, runId],
    queryFn: () => api.profile(id, runId),
    enabled: Number.isFinite(id),
  })
  usePageTitle(profile.data?.player.display_name ?? 'Player')

  if (profile.isLoading) return <LoadingState />
  if (!profile.data) {
    return (
      <EmptyState title="Player not found">
        <ErrorText error={profile.error} />
        <Link to="/stats" className="btn-secondary">
          Back to Stats
        </Link>
      </EmptyState>
    )
  }
  const p = profile.data
  return (
    <div className="flex flex-col gap-5">
      <Hero profile={p} />
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/stats" className="text-sm text-slate-400 hover:text-slate-200">
          ← Stats
        </Link>
        <select
          className="input ml-auto"
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
      </div>
      <Numbers profile={p} oneRun={runId != null} />
      <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
        <div className="flex flex-col gap-5">
          {p.gold_timeline && p.gold_timeline.length > 1 && (
            <Section title="Gold this run" right={<GoldBadge amount={p.gold_timeline.at(-1)!.balance} />}>
              <GoldChart points={p.gold_timeline.map((g) => g.balance)} />
            </Section>
          )}
          <RecentGames profile={p} />
        </div>
        <div className="flex flex-col gap-5">
          <Champions profile={p} />
          <Items profile={p} />
          <Runs profile={p} />
        </div>
      </div>
    </div>
  )
}

function Hero({ profile: p }: { profile: PlayerProfile }) {
  const champs = useChampionMap()
  const fav = p.champions[0] ? champs.get(p.champions[0].champion_id) : undefined
  const art = fav ? splashUrl({ champion_id: fav.id, image_url: fav.image_url }) : null
  return (
    <div className="relative -mx-4 overflow-hidden sm:mx-0 sm:rounded-sm" style={{ borderTop: `3px solid ${teamColor(p.player.id)}` }}>
      {art ? (
        <img src={art} alt="" className="absolute inset-0 h-full w-full object-cover object-[50%_25%]" />
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-hex-800 to-slate-900" />
      )}
      <div className="absolute inset-0 bg-gradient-to-r from-slate-950 via-slate-950/80 to-slate-950/20" />
      <div className="relative flex flex-col gap-1 px-5 py-8 sm:px-8 sm:py-10">
        <span className="broadcast-tag self-start" style={{ ['--tag' as string]: teamColor(p.player.id) }}>Player profile</span>
        <h1 className="font-display text-4xl tracking-[0.06em] text-white sm:text-5xl">{p.player.display_name}</h1>
        <TitlePicker playerId={p.player.id} />
        <p className="text-sm text-slate-300">
          {p.player.riot_id ?? 'No Riot ID linked'}
          {p.player.riot_id && !p.player.linked && <span className="text-amber-300"> · not linked yet</span>}
        </p>
        {fav && <p className="mt-2 text-xs text-slate-400">Most played: {fav.name}</p>}
      </div>
    </div>
  )
}

/** The player's shown title (from an achievement they've unlocked), with a picker. */
function TitlePicker({ playerId }: { playerId: number }) {
  const report = useAchievements()
  const players = usePlayerMap()
  const update = useAction((title: string | null) => api.updatePlayer(playerId, { title }))
  const { isOwner, myPlayerId } = useAccess()
  const current = players.get(playerId)?.title ?? null
  const unlocked = (report.data?.players[String(playerId)] ?? [])
    .map((u) => report.data!.catalog.find((a) => a.id === u.id))
    .filter((a): a is NonNullable<typeof a> => !!a)
  const shown = unlocked.find((a) => a.id === current)
  if (!unlocked.length) return null
  // Only the player (or the site owner) picks their title; everyone else just sees it.
  const canEdit = isOwner || myPlayerId === playerId
  return (
    <div className="flex flex-wrap items-center gap-2">
      {shown && <span className="font-display text-lg tracking-wide text-gold-300 italic">“{shown.title}”</span>}
      {canEdit && <select
        className="input py-1 text-xs"
        aria-label="Title"
        value={current ?? ''}
        disabled={update.isPending}
        onChange={(e) => update.mutate(e.target.value || null)}
      >
        <option value="">{shown ? 'No title' : `Choose a title (${unlocked.length} unlocked)`}</option>
        {unlocked.map((a) => (
          <option key={a.id} value={a.id}>
            {a.icon} {a.title}
          </option>
        ))}
      </select>}
    </div>
  )
}

function Numbers({ profile: p, oneRun }: { profile: PlayerProfile; oneRun: boolean }) {
  const s = p.stats
  return (
    <div className="card grid grid-cols-3 gap-4 sm:grid-cols-4 lg:grid-cols-7">
      <Stat label="Record" value={s.games ? `${s.wins}–${s.losses}` : '—'} accent />
      <Stat label="Win rate" value={pct(s.win_rate)} />
      <Stat label="KDA" value={num(s.kda, 2)} />
      <Stat label="Avg grade" value={s.avg_grade ?? '—'} />
      <Stat label="Champs lost" value={s.eliminated_champions.length} />
      <Stat label="Tokens earned" value={p.tokens_earned} />
      {oneRun ? (
        <Stat label="Gold earned" value={s.gold_earned == null ? '—' : s.gold_earned.toLocaleString()} />
      ) : (
        <Stat label="Runs" value={p.runs.length} />
      )}
    </div>
  )
}

/** Balance after each gold change, as a small area chart. */
function GoldChart({ points }: { points: number[] }) {
  const max = Math.max(...points, 1)
  const min = Math.min(...points, 0)
  const x = (i: number) => (i / (points.length - 1)) * 100
  const y = (v: number) => 38 - ((v - min) / (max - min || 1)) * 34
  const line = points.map((v, i) => `${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(' ')
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-36 w-full" role="img" aria-label="Gold balance over time">
      <defs>
        <linearGradient id="gold-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#c89b3c" stopOpacity="0.45" />
          <stop offset="1" stopColor="#c89b3c" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,40 ${line} 100,40`} fill="url(#gold-area)" />
      <polyline points={line} fill="none" stroke="#f0e6d2" strokeWidth="1.5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  )
}

function RecentGames({ profile: p }: { profile: PlayerProfile }) {
  const champs = useChampionMap()
  return (
    <Section title={`Games (${p.games.length})`}>
      {p.games.length === 0 ? (
        <p className="text-sm text-slate-400">No challenge games yet.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-white/5">
          {p.games.map((g) => {
            const c = g.champion_id ? champs.get(g.champion_id) : undefined
            const won = g.status === 'won'
            return (
              <li key={g.game_id} className="flex items-center gap-3 py-2 text-sm">
                <span
                  className={`w-9 shrink-0 rounded-md py-0.5 text-center text-xs font-bold ${
                    won ? 'bg-hex-800/80 text-hex-100' : 'bg-red-950/80 text-red-200'
                  }`}
                >
                  {won ? 'W' : 'L'}
                </span>
                <ChampionPortrait champion={c} size="sm" dim={g.eliminated} />
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="flex items-center gap-1.5 truncate font-medium">
                    {c?.name ?? 'Unknown'}
                    {g.eliminated && <SkullIcon className="h-3.5 w-3.5 text-red-300" aria-label="eliminated" />}
                    {g.token_earned && <span className="text-gold-300" title="Earned a revive token">✦</span>}
                  </span>
                  <span className="text-xs text-slate-500">
                    #{g.game_id} · {new Date(g.created_at).toLocaleDateString()}
                  </span>
                </div>
                {g.kda && <span className="hidden tabular-nums text-slate-300 sm:inline">{g.kda.join(' / ')}</span>}
                {g.grade && <span className="rounded-full bg-hex-800/70 px-1.5 text-xs text-hex-100">{g.grade}</span>}
                {g.gold != null && <GoldBadge amount={g.gold} />}
              </li>
            )
          })}
        </ul>
      )}
    </Section>
  )
}

function Champions({ profile: p }: { profile: PlayerProfile }) {
  const champs = useChampionMap()
  if (!p.champions.length) return null
  return (
    <Section title="Champions played">
      <div className="grid grid-cols-4 gap-2">
        {p.champions.slice(0, 12).map((c) => {
          const champ = champs.get(c.champion_id)
          const art = champ ? loadingUrl({ champion_id: champ.id, image_url: champ.image_url }) : null
          return (
            <div key={c.champion_id} className="relative aspect-[3/4] overflow-hidden rounded-lg bg-slate-800" title={champ?.name}>
              {art && <img src={art} alt="" loading="lazy" className="h-full w-full object-cover object-[50%_15%]" />}
              <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 to-transparent px-1 pt-3 pb-0.5 text-center text-[10px] font-bold tabular-nums">
                {c.wins}–{c.games - c.wins}
              </span>
            </div>
          )
        })}
      </div>
    </Section>
  )
}

function Items({ profile: p }: { profile: PlayerProfile }) {
  const items = p.items
  const owned = ITEM_ORDER.filter((t) => items?.[t]?.bought)
  if (!items || !owned.length) return null  // null: someone else's items are private
  return (
    <Section title="Shop items">
      <ul className="flex flex-col gap-2">
        {owned.map((t) => (
          <li key={t} className="flex items-center gap-3 text-sm">
            <ItemArt type={t} size={32} />
            <span className="flex-1">{ITEM_META[t].name}</span>
            <span className="text-slate-400 tabular-nums">
              {items[t]!.bought} bought · {items[t]!.used} used
            </span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

function Runs({ profile: p }: { profile: PlayerProfile }) {
  if (!p.runs.length) return null
  return (
    <Section title="Runs">
      <ul className="flex flex-col gap-1.5">
        {p.runs.map((r) => (
          <li key={r.run_id} className="flex items-center gap-2 text-sm">
            <span className="flex-1 truncate">
              {r.name}
              {r.status === 'ended' && <span className="text-slate-500"> (ended)</span>}
            </span>
            <span className="text-slate-400 tabular-nums">
              {r.wins}–{r.games - r.wins}
            </span>
            <Link to={`/runs/${r.run_id}/recap`} className="text-xs text-gold-300 hover:underline">
              Recap
            </Link>
          </li>
        ))}
      </ul>
    </Section>
  )
}
