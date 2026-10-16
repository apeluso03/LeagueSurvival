import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { LockInMoment } from '../components/LockIn'
import { LowerThird } from '../components/LowerThird'
import { ResultWatcher } from '../components/StatusBanners'
import { useChampionMap, useTeamColors } from '../hooks/queries'
import { loadingUrl } from '../lib/champions'
import { teamColor } from '../lib/teams'
import type { Game } from '../types'

const POLL_MS = 4000

/**
 * Stream overlay for OBS (add it as a Browser Source, 1920x1080). Transparent page with the run's
 * score bug, the current picks, and the VICTORY / ELIMINATED / LOCKED IN moments.
 * ?picks=0 hides the picks, ?moments=0 hides the moments.
 */
export function OverlayPage() {
  const [params] = useSearchParams()
  const showPicks = params.get('picks') !== '0'
  const showMoments = params.get('moments') !== '0'
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
      {showPicks && game.data?.status === 'pending' && <OverlayPicks game={game.data} />}
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
