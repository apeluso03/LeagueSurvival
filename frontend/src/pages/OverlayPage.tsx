import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { LockInMoment } from '../components/LockIn'
import { LowerThird } from '../components/LowerThird'
import { ResultWatcher } from '../components/StatusBanners'
import { useChampionMap, useTeamColors } from '../hooks/queries'
import { loadingUrl } from '../lib/champions'
import { BLUE, DRAGON_COLOR, RED, SIDE_COLOR, clock, goldShort } from '../lib/live'
import { teamColor } from '../lib/teams'
import type { Game, LiveState, TeamId } from '../types'

const POLL_MS = 4000

/**
 * Stream overlay for OBS (add it as a Browser Source, 1920x1080). Transparent page with the run's
 * score bug, the current picks, and the VICTORY / ELIMINATED / LOCKED IN moments.
 * During a tracked game it adds a live score bar (kills, clock, gold lead, towers, dragons).
 * ?picks=0 hides the picks, ?moments=0 hides the moments, ?live=0 hides the live bar.
 */
export function OverlayPage() {
  const [params] = useSearchParams()
  const showPicks = params.get('picks') !== '0'
  const showMoments = params.get('moments') !== '0'
  const showLive = params.get('live') !== '0'
  useTeamColors()

  // Transparent page while the overlay is open.
  useEffect(() => {
    document.documentElement.classList.add('overlay-mode')
    document.title = 'LoL Survival overlay'
    return () => document.documentElement.classList.remove('overlay-mode')
  }, [])

  const settings = useQuery({ queryKey: ['settings'], queryFn: api.settings, refetchInterval: POLL_MS })
  const runId = settings.data?.active_run_id
  const run = useQuery({ queryKey: ['run', runId], queryFn: () => api.run(runId!), enabled: runId != null, refetchInterval: POLL_MS })
  const gameId = run.data?.pending_game_id
  const game = useQuery({ queryKey: ['game', gameId], queryFn: () => api.game(gameId!), enabled: gameId != null, refetchInterval: POLL_MS })
  const r = run.data
  const live = useQuery({ queryKey: ['live'], queryFn: api.live, refetchInterval: 3000, enabled: showLive })
  const liveState = live.data?.live && live.data.live.ended_at == null ? live.data.live.state : null

  return (
    <div className="overlay-root">
      {r && (
        <div className="overlay-bug">
          <span className="broadcast-tag" style={{ ['--tag' as string]: '#e5283c' }}>
            <span className="live-dot" /> Live
          </span>
          <div className="score-bug">
            <span className="sb-run flex">{r.name}</span>
            <span className="sb-cell">
              <b className="text-gold-300">{r.win_count}</b>
              <small>Wins</small>
            </span>
            <span className="sb-cell">
              <b className="text-white">{r.current_streak}</b>
              <small>Streak</small>
            </span>
            <span className="sb-cell">
              <b className="text-white">
                {r.alive_count}/{r.total_count}
              </b>
              <small>Alive</small>
            </span>
            <span className="sb-cell">
              <b className="text-white">{r.tokens_available}</b>
              <small>Tokens</small>
            </span>
          </div>
        </div>
      )}
      {showLive && liveState && <OverlayLive st={liveState} />}
      {showPicks && game.data?.status === 'pending' && !liveState && <OverlayPicks game={game.data} />}
      {showMoments && (
        <>
          <ResultWatcher toasts={false} />
          <OverlayLockIn game={game.data} />
        </>
      )}
    </div>
  )
}

function OverlayPicks({ game }: { game: Game }) {
  const champs = useChampionMap()
  return (
    <div className="overlay-picks">
      {game.assignments.map((a) => {
        const cid = a.played_champion_id ?? a.options[0]
        const c = champs.get(cid)
        const art = c ? loadingUrl({ champion_id: c.id, image_url: c.image_url }) : null
        return (
          <div key={a.player_id} className="overlay-pick" style={{ '--team': teamColor(a.player_id) } as CSSProperties}>
            <div className="loading-frame w-24" style={{ backgroundImage: art ? `url(${art})` : undefined }} />
            <LowerThird playerId={a.player_id} size="sm" sub={a.played_champion_id ? c?.name : 'Picking'} />
          </div>
        )
      })}
    </div>
  )
}

/** Broadcast-style live score bar: kills, clock and item-gold lead, towers and dragons per side. */
function OverlayLive({ st }: { st: LiveState }) {
  const blue = st.teams['100']
  const red = st.teams['200']
  const lead = blue.gold - red.gold
  const side = (team: TeamId, right: boolean) => {
    const t = team === BLUE ? blue : red
    return (
      <div className={`flex items-center gap-3 ${right ? 'flex-row-reverse' : ''}`}>
        <b className="font-display text-4xl text-white tabular-nums">{t.kills}</b>
        <span className="flex flex-col text-xs text-slate-200 tabular-nums" style={{ alignItems: right ? 'flex-end' : 'flex-start' }}>
          <span>
            {goldShort(t.gold)} gold · {t.towers} {t.towers === 1 ? 'tower' : 'towers'}
          </span>
          <span className="flex gap-0.5">
            {t.dragons.map((d, i) => (
              <span key={i} className="h-2.5 w-2.5 rotate-45" style={{ background: DRAGON_COLOR[d] ?? '#8a93a5' }} />
            ))}
          </span>
        </span>
      </div>
    )
  }
  return (
    <div className="overlay-live" style={{ '--blue': SIDE_COLOR[BLUE], '--red': SIDE_COLOR[RED] } as CSSProperties}>
      {side(BLUE, false)}
      <div className="flex flex-col items-center px-4">
        <b className="font-display text-2xl text-white tabular-nums">{clock(st.game_time)}</b>
        <small className="text-xs text-slate-300 tabular-nums">
          {lead === 0 ? 'Even' : `${lead > 0 ? 'Blue' : 'Red'} +${goldShort(Math.abs(lead))}`}
        </small>
      </div>
      {side(RED, true)}
    </div>
  )
}

/** LOCKED IN when the last pick of the pending game comes in. */
function OverlayLockIn({ game }: { game: Game | undefined }) {
  const all = !!game && game.status === 'pending' && game.assignments.every((a) => a.played_champion_id)
  const prev = useRef<{ id: number; all: boolean } | null>(null)
  const [show, setShow] = useState<Game | null>(null)
  useEffect(() => {
    if (!game) return
    const before = prev.current
    prev.current = { id: game.id, all }
    if (before?.id === game.id && !before.all && all) setShow(game)
  }, [game, all])
  return show ? <LockInMoment key={show.id} game={show} onDone={() => setShow(null)} /> : null
}
