import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { LowerThird } from '../components/LowerThird'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState } from '../components/ui'
import { useChampionMap, usePlayerMap } from '../hooks/queries'
import { usePageTitle } from '../hooks/usePageTitle'
import { splashUrl } from '../lib/champions'
import { num, pct } from '../lib/stats'
import { teamColor } from '../lib/teams'
import type { Wrapped } from '../types'

const SLIDE_MS = 7000

const monthName = (m: string) => {
  const [y, mo] = m.split('-').map(Number)
  return new Date(Date.UTC(y, mo - 1, 1)).toLocaleDateString(undefined, { month: 'long', year: 'numeric', timeZone: 'UTC' })
}

/** Pick a roast line that stays the same for a month (so it doesn't change on every render). */
function pickLine(lines: string[], seed: string) {
  let h = 0
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return lines[h % lines.length]
}

type Slide = { key: string; art?: string | null; color?: string; body: ReactNode }

/** Monthly Wrapped: a month of the challenge as tap-through story slides. */
export function WrappedPage() {
  const [month, setMonth] = useState<string | undefined>(undefined)
  const wrapped = useQuery({ queryKey: ['wrapped', month ?? 'latest'], queryFn: () => api.wrapped(month) })
  usePageTitle('Wrapped')
  if (wrapped.isLoading) return <LoadingState />
  if (!wrapped.data) return <ErrorText error={wrapped.error} />
  const w = wrapped.data
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/trophies" className="text-sm text-slate-400 hover:text-slate-200">
          ← Trophies
        </Link>
        <span className="broadcast-tag" style={{ ['--tag' as string]: 'var(--color-gold-600)' }}>
          Survival Wrapped
        </span>
        <select className="input ml-auto" aria-label="Month" value={w.month} onChange={(e) => setMonth(e.target.value)}>
          {(w.months.includes(w.month) ? w.months : [w.month, ...w.months]).map((m) => (
            <option key={m} value={m}>
              {monthName(m)}
            </option>
          ))}
        </select>
      </div>
      {w.games === 0 ? (
        <EmptyState title={`No games in ${monthName(w.month)}`}>
          <p className="text-sm text-slate-400">Play some challenge games and come back for your Wrapped.</p>
        </EmptyState>
      ) : (
        <Story key={w.month} w={w} />
      )}
    </div>
  )
}

function Story({ w }: { w: Wrapped }) {
  const champs = useChampionMap()
  const players = usePlayerMap()
  const name = useCallback((pid: number) => players.get(pid)?.display_name ?? `Player ${pid}`, [players])
  const art = useCallback(
    (cid: string | null | undefined) => {
      const c = cid ? champs.get(cid) : undefined
      return c ? splashUrl({ champion_id: c.id, image_url: c.image_url }) : null
    },
    [champs],
  )
  const champName = (cid: string | null | undefined) => (cid ? (champs.get(cid)?.name ?? cid) : 'someone')
  const losses = w.games - w.wins

  const slides = useMemo<Slide[]>(() => {
    const s: Slide[] = []
    const big = (t: ReactNode) => <div className="wrapped-big">{t}</div>
    s.push({
      key: 'intro',
      art: art(w.most_played?.champion_id),
      body: (
        <>
          <span className="wrapped-kicker">Survival Wrapped</span>
          {big(monthName(w.month))}
          <p className="wrapped-line">
            {w.games} games. {w.players.length} players. Let's see how it went.
          </p>
        </>
      ),
    })
    s.push({
      key: 'record',
      color: 'var(--color-hex-500)',
      body: (
        <>
          <span className="wrapped-kicker">The record</span>
          <div className="flex items-end justify-center gap-6">
            <div className="text-center">
              {big(<span className="text-hex-200">{w.wins}</span>)}
              <span className="wrapped-small">wins</span>
            </div>
            <div className="text-center">
              {big(<span className="text-red-300">{losses}</span>)}
              <span className="wrapped-small">losses</span>
            </div>
          </div>
          <p className="wrapped-line">
            {pct(w.wins / w.games)} win rate, best streak of <b>{w.best_streak}</b>.{' '}
            {pickLine(
              w.wins >= losses
                ? ['Not bad at all.', 'The wheel fears you.', 'Respectable. Suspiciously so.']
                : ['The wheel was not kind.', 'Character-building month.', "We've all been there. Mostly you."],
              w.month,
            )}
          </p>
        </>
      ),
    })
    if (w.most_played) {
      const m = w.most_played
      s.push({
        key: 'most-played',
        art: art(m.champion_id),
        body: (
          <>
            <span className="wrapped-kicker">Most played champion</span>
            {big(champName(m.champion_id))}
            <p className="wrapped-line">
              Rolled into {m.games} games and won {m.wins}.{' '}
              {pickLine(['The wheel has a favourite.', 'Destiny, or just bad luck?', "At this point it's a main."], m.champion_id)}
            </p>
          </>
        ),
      })
    }
    if (w.mvp) {
      const p = w.mvp
      s.push({
        key: 'mvp',
        art: art(p.top_champion),
        color: teamColor(p.player_id),
        body: (
          <>
            <span className="wrapped-kicker">👑 MVP of the month</span>
            {big(name(p.player_id))}
            <p className="wrapped-line">
              {p.wins}–{p.games - p.wins} ({pct(p.wins / p.games)}){p.kda != null && `, ${num(p.kda, 2)} KDA`}. Carried. Possibly literally.
            </p>
          </>
        ),
      })
    }
    if (w.top_killer?.kills) {
      const p = w.top_killer
      s.push({
        key: 'killer',
        color: teamColor(p.player_id),
        art: art(p.top_champion),
        body: (
          <>
            <span className="wrapped-kicker">⚔️ Top killer</span>
            {big(name(p.player_id))}
            <p className="wrapped-line">
              <b>{p.kills}</b> kills this month{w.pentas > 0 && `, and the group found ${w.pentas} penta${w.pentas > 1 ? 's' : ''}`}.
            </p>
          </>
        ),
      })
    }
    if (w.feeder?.avg_deaths != null) {
      const p = w.feeder
      s.push({
        key: 'feeder',
        color: '#c8102e',
        body: (
          <>
            <span className="wrapped-kicker">🪦 Most time spent grey</span>
            {big(name(p.player_id))}
            <p className="wrapped-line">
              {num(p.avg_deaths, 1)} deaths a game.{' '}
              {pickLine(
                ['The respawn timer knows them by name.', 'A generous donor to the enemy team.', 'Fountain enthusiast.'],
                `${w.month}${p.player_id}`,
              )}
            </p>
          </>
        ),
      })
    }
    if (w.best_duo) {
      const d = w.best_duo
      s.push({
        key: 'duo',
        color: teamColor(d.players[0]),
        body: (
          <>
            <span className="wrapped-kicker">Best duo</span>
            {big(`${name(d.players[0])} + ${name(d.players[1])}`)}
            <p className="wrapped-line">
              {d.wins}–{d.games - d.wins} together.
              {w.worst_duo &&
                ` Meanwhile ${name(w.worst_duo.players[0])} + ${name(w.worst_duo.players[1])} went ${w.worst_duo.wins}–${
                  w.worst_duo.games - w.worst_duo.wins
                }. Maybe don't queue together.`}
            </p>
          </>
        ),
      })
    }
    if (w.worst_game) {
      const g = w.worst_game
      s.push({
        key: 'worst',
        art: art(g.champion_id),
        color: '#c8102e',
        body: (
          <>
            <span className="wrapped-kicker">The game we don't talk about</span>
            {big(`${g.kills}/${g.deaths}/${g.assists}`)}
            <p className="wrapped-line">
              {name(g.player_id)} on {champName(g.champion_id)}, game {g.game_id}. {g.won ? 'Somehow they won.' : 'It went as you think.'}
            </p>
          </>
        ),
      })
    }
    if (w.gold_spent > 0) {
      s.push({
        key: 'gold',
        color: 'var(--color-gold-600)',
        body: (
          <>
            <span className="wrapped-kicker">💰 Shopping spree</span>
            {big(<span className="gold-text">{w.gold_spent.toLocaleString()}</span>)}
            <p className="wrapped-line">
              gold spent on {w.items_bought} item{w.items_bought === 1 ? '' : 's'}
              {w.reroll_gold > 0 && ` (${w.reroll_gold.toLocaleString()} of it on Rerolls. The wheel still won.)`}.
            </p>
          </>
        ),
      })
    }
    if (w.champions_lost > 0) {
      s.push({
        key: 'graveyard',
        color: '#454e5e',
        body: (
          <>
            <span className="wrapped-kicker">The graveyard grew</span>
            {big(w.champions_lost)}
            <p className="wrapped-line">champions eliminated. Rest in peace, every one of them.</p>
          </>
        ),
      })
    }
    s.push({
      key: 'players',
      body: (
        <>
          <span className="wrapped-kicker">Everyone's month</span>
          <div className="flex w-full flex-col gap-2">
            {w.players.map((p) => (
              <div key={p.player_id} className="flex items-center gap-3 bg-black/40 p-2 text-left">
                <ChampionPortrait champion={p.top_champion ? champs.get(p.top_champion) : undefined} size="sm" />
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <LowerThird playerId={p.player_id} size="sm" sub={`${p.wins}–${p.games - p.wins}`} />
                  <span className="text-[11px] text-slate-300">
                    Most played {champName(p.top_champion)}
                    {p.kda != null && ` · ${num(p.kda, 2)} KDA`} · {p.champions_lost} lost
                  </span>
                </div>
              </div>
            ))}
          </div>
        </>
      ),
    })
    s.push({
      key: 'outro',
      art: art(w.mvp?.top_champion ?? w.most_played?.champion_id),
      body: (
        <>
          <span className="wrapped-kicker">That's a wrap</span>
          {big('See you next month')}
          <p className="wrapped-line">Same wheel. Same pain. Different champs (hopefully).</p>
        </>
      ),
    })
    return s
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [w, art, name])

  const [index, setIndex] = useState(0)
  const next = useCallback(() => setIndex((i) => Math.min(slides.length - 1, i + 1)), [slides.length])
  const prev = useCallback(() => setIndex((i) => Math.max(0, i - 1)), [])
  useEffect(() => {
    if (index >= slides.length - 1) return
    const t = setTimeout(next, SLIDE_MS)
    return () => clearTimeout(t)
  }, [index, next, slides.length])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === ' ') (e.preventDefault(), next())
      if (e.key === 'ArrowLeft') prev()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, prev])

  const slide = slides[index]
  return (
    <div className="mx-auto w-full max-w-md">
      <div className="wrapped-story relative overflow-hidden" style={{ '--slide': slide.color ?? 'var(--color-hex-600)' } as CSSProperties}>
        {slide.art && <img key={`art-${slide.key}`} src={slide.art} alt="" className="wrapped-art" />}
        <div className="wrapped-shade" />
        <div className="absolute inset-x-3 top-3 z-10 flex gap-1">
          {slides.map((sl, i) => (
            <span key={sl.key} className="wrapped-progress">
              <span
                className={i < index ? 'is-done' : i === index ? 'is-playing' : ''}
                style={i === index ? { animationDuration: `${SLIDE_MS}ms` } : undefined}
                key={i === index ? `${sl.key}-${index}` : sl.key}
              />
            </span>
          ))}
        </div>
        <div key={`body-${slide.key}`} className="wrapped-body relative z-10 flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
          {slide.body}
        </div>
        <button className="absolute inset-y-0 left-0 z-20 w-1/3" aria-label="Previous" onClick={prev} />
        <button className="absolute inset-y-0 right-0 z-20 w-2/3" aria-label="Next" onClick={next} />
      </div>
      <p className="mt-2 text-center text-xs text-slate-500">
        Tap or use ← → · {index + 1} / {slides.length}
      </p>
    </div>
  )
}
