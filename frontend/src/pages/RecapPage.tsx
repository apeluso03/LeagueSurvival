import { useQuery } from '@tanstack/react-query'
import { useRef, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { LowerThird } from '../components/LowerThird'
import { PlayerLink } from '../components/PlayerLink'
import { CoinIcon } from '../components/icons'
import { EmptyState, ErrorText, LoadingState } from '../components/ui'
import { useChampionMap, usePlayerMap } from '../hooks/queries'
import { usePageTitle } from '../hooks/usePageTitle'
import { loadingUrl, splashUrl } from '../lib/champions'
import { num, pct } from '../lib/stats'
import { teamColor } from '../lib/teams'
import type { RecapAward, RecapPlayer, RunRecap } from '../types'

const AWARD_ICONS: Record<string, string> = {
  mvp: '👑',
  kda: '🎯',
  grade: '🏅',
  multikill: '⚔️',
  reaper: '💀',
  spender: '💰',
  first: '🩸',
  survivor: '🛡️',
  workhorse: '🐎',
}

function dateRange(start: string, end: string | null) {
  const fmt = (d: Date) => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const a = new Date(start)
  const b = end ? new Date(end) : new Date()
  const days = Math.max(1, Math.round((b.getTime() - a.getTime()) / 86_400_000))
  return `${fmt(a)} – ${end ? fmt(b) : 'now'} · ${days} day${days > 1 ? 's' : ''}`
}

let fontCSS: Promise<string> | null = null
/** The League display font as an inline @font-face, so it shows up in the saved image. */
function leagueFontCSS() {
  fontCSS ??= fetch('/fonts/League.otf')
    .then((r) => r.blob())
    .then(
      (blob) =>
        new Promise<string>((resolve) => {
          const reader = new FileReader()
          reader.onload = () => resolve(`@font-face { font-family: "League"; src: url(${reader.result}) format("opentype"); }`)
          reader.readAsDataURL(blob)
        }),
    )
    .catch(() => '')
  return fontCSS
}

/** A run's story at a glance: totals, the win/loss timeline, awards and every player's line. */
export function RecapPage() {
  const id = Number(useParams().id)
  const recap = useQuery({ queryKey: ['recap', id], queryFn: () => api.recap(id), enabled: Number.isFinite(id) })
  usePageTitle(recap.data ? `${recap.data.run.name} recap` : 'Recap')
  const sheet = useRef<HTMLDivElement>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<unknown>(null)

  if (recap.isLoading) return <LoadingState />
  if (!recap.data) {
    return (
      <EmptyState title="Run not found">
        <ErrorText error={recap.error} />
      </EmptyState>
    )
  }
  const r = recap.data

  const save = async () => {
    if (!sheet.current) return
    setSaving(true)
    setSaveError(null)
    try {
      const { toPng } = await import('html-to-image') // only loaded when someone saves
      // Hand it our own font instead of letting it read the (cross-origin) Google Fonts stylesheet.
      const url = await toPng(sheet.current, {
        pixelRatio: 2,
        backgroundColor: '#05070b',
        cacheBust: true,
        fontEmbedCSS: await leagueFontCSS(),
      })
      const a = document.createElement('a')
      a.href = url
      a.download = `${r.run.name.replace(/[^\w-]+/g, '-')}-recap.png`
      a.click()
    } catch (e) {
      setSaveError(e instanceof Error ? e : new Error("Couldn't make the image"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Link to="/stats" className="text-sm text-slate-400 hover:text-slate-200">
          ← Stats
        </Link>
        <button className="btn-primary ml-auto" disabled={saving} onClick={save}>
          {saving ? 'Saving...' : 'Save as image'}
        </button>
      </div>
      <ErrorText error={saveError} />
      <div ref={sheet} className="flex flex-col gap-5 bg-[#05070b] p-1 sm:p-3">
        <Hero recap={r} />
        <Totals recap={r} />
        <div className={`grid gap-5 ${r.awards.some((a) => a.id === 'mvp') ? 'lg:grid-cols-[1fr_1.15fr]' : ''}`}>
          <MvpSpotlight recap={r} />
          <StatComparison players={r.players} />
        </div>
        <Timeline recap={r} />
        <Awards awards={r.awards} players={r.players} />
        <PlayerTable players={r.players} />
        <p className="font-display text-center text-xs tracking-[0.3em] text-slate-600 uppercase">
          Hardcore <span className="text-hex-400">Draft</span> · Post-game
        </p>
      </div>
    </div>
  )
}

/** Post-game header: run name, dates and the run's scoreline like a broadcast's final score. */
function Hero({ recap: r }: { recap: RunRecap }) {
  const champs = useChampionMap()
  const featured = r.awards.find((a) => a.id === 'workhorse' || a.id === 'survivor')?.champion_id
  const champ = featured ? champs.get(featured) : undefined
  const art = champ ? splashUrl({ champion_id: champ.id, image_url: champ.image_url }) : null
  const t = r.totals
  return (
    <div className="postgame-hero relative overflow-hidden">
      {art ? (
        <img src={art} alt="" crossOrigin="anonymous" className="absolute inset-0 h-full w-full object-cover object-[50%_25%] opacity-60" />
      ) : (
        <div className="absolute inset-0 bg-gradient-to-br from-hex-800 to-slate-900" />
      )}
      <div className="absolute inset-0 bg-gradient-to-r from-[#05070b] via-[#05070b]/80 to-[#05070b]/40" />
      <div className="relative flex flex-col gap-5 px-5 py-7 sm:flex-row sm:items-end sm:justify-between sm:px-8 sm:py-9">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            <span className="broadcast-tag" style={{ ['--tag' as string]: 'var(--color-hex-400)' }}>
              Post-game
            </span>
            <span className="broadcast-tag" style={{ ['--tag' as string]: r.run.status === 'ended' ? '#c8102e' : '#454e5e' }}>
              {r.run.status === 'ended' ? 'Run over' : 'Still going'}
            </span>
          </div>
          <h1 className="font-display text-4xl tracking-[0.06em] text-white sm:text-6xl">{r.run.name}</h1>
          <p className="text-sm text-slate-300">{dateRange(r.run.started_at, r.run.ended_at)}</p>
        </div>
        <div className="scoreline">
          <div>
            <b className="text-hex-200">{t.wins}</b>
            <small>Wins</small>
          </div>
          <span className="scoreline-dash">–</span>
          <div>
            <b className="text-red-400">{t.losses}</b>
            <small>Losses</small>
          </div>
          <div className="scoreline-streak">
            <b className="gold-text">{t.best_streak}</b>
            <small>Best streak</small>
          </div>
        </div>
      </div>
    </div>
  )
}

function Totals({ recap: { totals: t } }: { recap: RunRecap }) {
  const items: [string, string | number][] = [
    ['Games', t.games],
    ['Champs left', `${t.alive}/${t.total}`],
    ['Eliminated', t.total - t.alive],
    ['Tokens used', `${t.tokens_used}/${t.tokens_earned}`],
    ['Shields saved', t.shields_saved],
    ['Items bought', t.items_bought],
  ]
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden bg-white/[0.06] sm:grid-cols-4 lg:grid-cols-7">
      {items.map(([label, value]) => (
        <div key={label} className="flex flex-col bg-[#0b0e14] px-4 py-3">
          <span className="font-display text-2xl text-white tabular-nums">{value}</span>
          <span className="text-[10px] font-bold tracking-[0.14em] text-slate-400 uppercase">{label}</span>
        </div>
      ))}
      <div className="flex flex-col bg-[#0b0e14] px-4 py-3 shadow-[inset_0_-2px_0_var(--color-gold-400)]">
        <span className="font-display flex items-center gap-1.5 text-2xl text-gold-300 tabular-nums">
          <CoinIcon className="h-5 w-5" />
          {t.gold_earned.toLocaleString()}
        </span>
        <span className="text-[10px] font-bold tracking-[0.14em] text-slate-400 uppercase">Gold earned</span>
      </div>
    </div>
  )
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="postgame-title">{children}</h2>
}

/** Every game in order, like a series' match history. */
function Timeline({ recap: r }: { recap: RunRecap }) {
  if (!r.timeline.length) return null
  return (
    <section className="flex flex-col gap-2">
      <SectionTitle>Match history</SectionTitle>
      <div className="flex flex-wrap gap-1">
        {r.timeline.map((g, i) => (
          <span
            key={g.game_id}
            title={`Game ${g.game_id}: ${g.status === 'won' ? 'win' : 'loss'}`}
            className={`history-tile ${g.status === 'won' ? 'is-win' : 'is-loss'}`}
          >
            <small>{i + 1}</small>
            {g.status === 'won' ? 'W' : 'L'}
          </span>
        ))}
      </div>
    </section>
  )
}

/** The MVP in a big spotlight panel with their best champion. */
function MvpSpotlight({ recap: r }: { recap: RunRecap }) {
  const champs = useChampionMap()
  const award = r.awards.find((a) => a.id === 'mvp')
  const p = award ? r.players.find((x) => x.player_id === award.player_id) : undefined
  if (!award || !p) return null
  const cid = p.best_champion?.champion_id ?? p.top_champion
  const champ = cid ? champs.get(cid) : undefined
  const art = champ ? splashUrl({ champion_id: champ.id, image_url: champ.image_url }) : null
  const facts: [string, string][] = [
    ['Record', `${p.wins}–${p.losses}`],
    ['Win rate', pct(p.win_rate)],
    ['KDA', num(p.kda, 2)],
    ['Grade', p.avg_grade ?? '—'],
  ]
  return (
    <section className="mvp-panel relative flex min-h-64 flex-col justify-end overflow-hidden" style={{ ['--team' as string]: teamColor(p.player_id) }}>
      {art && <img src={art} alt="" crossOrigin="anonymous" className="absolute inset-0 h-full w-full object-cover object-[60%_20%]" />}
      <div className="absolute inset-0 bg-gradient-to-t from-[#05070b] via-[#05070b]/60 to-transparent" />
      <div className="relative flex flex-col gap-3 p-5">
        <span className="broadcast-tag self-start" style={{ ['--tag' as string]: 'var(--color-gold-500)' }}>
          👑 MVP of the run
        </span>
        <LowerThird playerId={p.player_id} sub={champ?.name} size="lg" />
        <div className="grid grid-cols-4 gap-px overflow-hidden bg-white/10">
          {facts.map(([label, value]) => (
            <div key={label} className="flex flex-col bg-black/70 px-3 py-2">
              <span className="font-display text-xl text-white">{value}</span>
              <span className="text-[10px] font-bold tracking-[0.12em] text-slate-400 uppercase">{label}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/** Broadcast-style stat comparison: one bar per player in their team colour, for a few key stats. */
function StatComparison({ players }: { players: RecapPlayer[] }) {
  const stats: { label: string; value: (p: RecapPlayer) => number | null; show: (p: RecapPlayer) => string }[] = [
    { label: 'Win rate', value: (p) => p.win_rate, show: (p) => pct(p.win_rate) },
    { label: 'KDA', value: (p) => p.kda, show: (p) => num(p.kda, 2) },
    { label: 'Gold earned', value: (p) => p.gold_earned, show: (p) => p.gold_earned?.toLocaleString() ?? '—' },
    { label: 'Champs lost', value: (p) => p.eliminations, show: (p) => String(p.eliminations) },
  ]
  // Skip stats with nothing to compare (all zero, or everyone the same).
  const shown = stats.filter((s) => new Set(players.map((p) => s.value(p) ?? 0)).size > 1)
  if (!shown.length || !players.length) return null
  return (
    <section className="card flex flex-col gap-4">
      <SectionTitle>Head to head</SectionTitle>
      {shown.map((s) => {
        const max = Math.max(...players.map((p) => s.value(p) ?? 0), 0.0001)
        return (
          <div key={s.label} className="flex flex-col gap-1.5">
            <span className="text-[11px] font-bold tracking-[0.14em] text-slate-400 uppercase">{s.label}</span>
            {players.map((p) => (
              <div key={p.player_id} className="grid grid-cols-[5.5rem_1fr_4rem] items-center gap-2 text-sm">
                <span className="font-display truncate tracking-wide text-slate-200 uppercase">
                  <PlayerLink id={p.player_id} />
                </span>
                <span className="h-2.5 overflow-hidden bg-white/[0.06]">
                  <span
                    className="stat-bar block h-full"
                    style={{ width: `${((s.value(p) ?? 0) / max) * 100}%`, ['--team' as string]: teamColor(p.player_id) }}
                  />
                </span>
                <span className="text-right text-white tabular-nums">{s.show(p)}</span>
              </div>
            ))}
          </div>
        )
      })}
    </section>
  )
}

function Awards({ awards, players }: { awards: RecapAward[]; players: RecapPlayer[] }) {
  const champs = useChampionMap()
  const names = usePlayerMap()
  const best = new Map(players.map((p) => [p.player_id, p.best_champion?.champion_id ?? p.top_champion]))
  const list = awards.filter((a) => a.id !== 'mvp') // the MVP has its own spotlight
  if (!list.length) return null
  return (
    <section className="flex flex-col gap-2">
      <SectionTitle>Awards</SectionTitle>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {list.map((a) => {
          // Champion awards show that champion; player awards show the player's best champ.
          const cid = a.champion_id ?? (a.player_id != null ? best.get(a.player_id) : undefined)
          const champ = cid ? champs.get(cid) : undefined
          const art = champ ? loadingUrl({ champion_id: champ.id, image_url: champ.image_url }) : null
          const who = a.champion_id ? champ?.name : a.player_id != null ? names.get(a.player_id)?.display_name : undefined
          const color = a.player_id != null ? teamColor(a.player_id) : 'var(--color-gold-400)'
          return (
            <div key={a.id} className="award-card relative aspect-[3/4] overflow-hidden bg-slate-800" style={{ ['--team' as string]: color }}>
              {art && <img src={art} alt="" crossOrigin="anonymous" className="absolute inset-0 h-full w-full object-cover object-[50%_15%]" />}
              <div className="absolute inset-0 bg-gradient-to-t from-[#05070b] via-[#05070b]/45 to-transparent" />
              <span className="absolute top-2 left-2 text-2xl drop-shadow" aria-hidden>
                {AWARD_ICONS[a.id] ?? '★'}
              </span>
              <div className="absolute inset-x-3 bottom-3 flex flex-col gap-1">
                <span className="broadcast-tag self-start" style={{ ['--tag' as string]: 'var(--color-gold-600)' }}>
                  {a.title}
                </span>
                <span className="font-display truncate text-xl tracking-wide text-white uppercase">{who ?? '—'}</span>
                <span className="text-xs text-slate-300">{a.text}</span>
                {a.champion_id && a.player_id != null && (
                  <span className="text-xs text-slate-400">by {names.get(a.player_id)?.display_name}</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function PlayerTable({ players }: { players: RecapPlayer[] }) {
  const rows = [...players].sort((a, b) => b.wins - a.wins || (b.win_rate ?? 0) - (a.win_rate ?? 0))
  const multi = (p: RecapPlayer) =>
    (['penta', 'quadra', 'triple'] as const)
      .filter((k) => p.multikills[k])
      .map((k) => `${p.multikills[k]} ${k}`)
      .join(', ') || '—'
  return (
    <section className="flex flex-col gap-2">
      <SectionTitle>Scoreboard</SectionTitle>
      <div className="overflow-x-auto">
        <table className="scoreboard w-full min-w-[720px] text-sm">
          <thead>
            <tr>
              {['Player', 'Record', 'Win %', 'KDA', 'Grade', 'Champs lost', 'Tokens', 'Gold earned', 'Spent', 'Multikills'].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.player_id} style={{ ['--team' as string]: teamColor(p.player_id) }}>
                <td className="font-display tracking-wide uppercase">
                  <PlayerLink id={p.player_id} />
                </td>
                <td>
                  {p.wins}–{p.losses}
                </td>
                <td>{pct(p.win_rate)}</td>
                <td>{num(p.kda, 2)}</td>
                <td>{p.avg_grade ?? '—'}</td>
                <td>{p.eliminations}</td>
                <td>{p.tokens_earned}</td>
                <td className="text-gold-300">{p.gold_earned?.toLocaleString() ?? '—'}</td>
                <td>{p.gold_spent?.toLocaleString() ?? '—'}</td>
                <td>{multi(p)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
