import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ChampionPicker } from '../components/ChampionPicker'
import { MatchSummaryView } from '../components/MatchSummary'
import { CaseReel } from '../components/CaseReel'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState, Modal } from '../components/ui'
import {
  useAction,
  useActiveRun,
  useChampionMap,
  useChampions,
  useGame,
  usePlayerMap,
  usePlayers,
  usePool,
  useRiotStatus,
} from '../hooks/queries'
import { preloadImages } from '../lib/preload'
import { SPIN_MS, buildStrip, randomLandingOffset } from '../lib/reel'
import { playReveal, playStart, unlock } from '../lib/sound'
import type { Assignment, Champion, Game, Run } from '../types'

type SpinStage = {
  key: number
  startAt: number // shared clock (performance.now) so every reel moves together
  reels: { playerId: number; strip: string[]; offset: number }[]
  done: boolean
  skipped: boolean
}

export function WheelsPage() {
  const { settings, run, runId } = useActiveRun()

  if (settings.isLoading || run.isLoading) return <LoadingState />
  if (!runId || !run.data) {
    return (
      <EmptyState title="No active run">
        <p className="text-sm text-slate-400">Add your players and start a run first.</p>
        <Link to="/settings" className="btn-primary">
          Go to Settings
        </Link>
      </EmptyState>
    )
  }
  return <Wheels run={run.data} challengeMode={settings.data!.challenge_mode} lastUsed={settings.data!.last_used_player_ids} />
}

function Wheels({ run, challengeMode, lastUsed }: { run: Run; challengeMode: boolean; lastUsed: number[] }) {
  const players = usePlayers()
  const pool = usePool(run.id)
  const pendingGame = useGame(run.pending_game_id)
  const champs = useChampionMap()
  const playerMap = usePlayerMap()
  const [selected, setSelected] = useState<number[] | null>(null)
  const [practice, setPractice] = useState<Assignment[] | null>(null)
  const [stage, setStage] = useState<SpinStage | null>(null)
  const [lastResolvedId, setLastResolvedId] = useState<number | null>(null)
  const spin = useAction((ids: number[]) => api.spin(run.id, ids))
  const qc = useQueryClient()

  // When the pending game gets resolved elsewhere (the backend's auto-matcher, or another tab),
  // show its result and refresh everything that the result may have changed.
  const prevPending = useRef(run.pending_game_id)
  useEffect(() => {
    const prev = prevPending.current
    prevPending.current = run.pending_game_id
    if (prev != null && run.pending_game_id == null) {
      setLastResolvedId(prev)
      void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'champions' })
    }
  }, [run.pending_game_id, qc])

  // Default to the last group, once players are loaded.
  useEffect(() => {
    if (selected === null && players.data) {
      const known = new Set(players.data.map((p) => p.id))
      setSelected(lastUsed.filter((id) => known.has(id)))
    }
  }, [players.data, lastUsed, selected])

  const alivePool = useMemo(
    () => (pool.data ?? []).filter((e) => e.status === 'alive').map((e) => e.champion_id),
    [pool.data],
  )
  // Decode every portrait the reels might show before anyone presses Spin.
  useEffect(() => preloadImages((pool.data ?? []).filter((e) => e.status === 'alive').map((e) => e.image_url)), [pool.data])

  const chosen = selected ?? []
  const toggle = (id: number) =>
    setSelected(chosen.includes(id) ? chosen.filter((p) => p !== id) : chosen.length < 5 ? [...chosen, id] : chosen)

  const pending = run.pending_game_id != null
  const canSpin = run.status === 'active' && !pending && chosen.length >= 2 && chosen.length <= 5

  const doSpin = () => {
    unlock() // browsers only allow sound after a click
    spin.mutate(chosen, {
      onSuccess: (res) => {
        setPractice(res.practice ? res.assignments : null)
        setLastResolvedId(null)
        // Skip the reels for people who asked their device for reduced motion.
        const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
        if (reduced) return setStage(null)
        const fillers = alivePool.length ? alivePool : res.assignments.flatMap((a) => a.options)
        setStage({
          key: Date.now(),
          // Motion starts a beat after the click, so mounting the reels never stutters on screen.
          startAt: performance.now() + 250,
          reels: res.assignments.map((a) => ({
            playerId: a.player_id,
            strip: buildStrip(fillers, a.options[0]),
            offset: randomLandingOffset(),
          })),
          done: false,
          skipped: false,
        })
        playStart()
      },
    })
  }

  const spinning = stage != null && !stage.done
  // Hold on the glowing winners for a moment before the option cards slide in.
  const finishSpin = () => {
    playReveal()
    const hold = stage?.skipped ? 500 : 1300
    const key = stage?.key
    setTimeout(() => setStage((s) => (s && s.key === key ? { ...s, done: true } : s)), hold)
  }

  const shownAssignments = pending ? pendingGame.data?.assignments : practice ?? undefined

  if (players.data && players.data.length < 2) {
    return (
      <EmptyState title="Add at least 2 players">
        <Link to="/settings" className="btn-primary">
          Go to Settings
        </Link>
      </EmptyState>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {run.status === 'ended' && (
        <p className="rounded-2xl bg-red-950/50 px-4 py-2.5 text-sm text-red-200 ring-1 ring-red-800/60 ring-inset">
          This run has ended with <b>{run.win_count}</b> wins. Start a new one in Settings.
        </p>
      )}

      {!pending && !spinning && (
        <section className="card flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">
              Who's playing? <span className="text-sm font-normal text-slate-400">({chosen.length}/5, need 2+)</span>
            </h2>
            {!challengeMode && (
              <span className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs tracking-wide uppercase">Practice spin</span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {players.data?.map((p) => {
              const on = chosen.includes(p.id)
              return (
                <button
                  key={p.id}
                  onClick={() => toggle(p.id)}
                  aria-pressed={on}
                  className={`rounded-full px-4 py-2 text-sm font-medium ring-1 transition duration-150 ring-inset active:scale-95 ${
                    on
                      ? 'bg-gradient-to-b from-gold-400 to-gold-600 text-slate-950 ring-gold-300/60'
                      : 'bg-white/5 text-slate-200 ring-slate-700 hover:bg-white/10'
                  }`}
                >
                  {p.display_name}
                </button>
              )
            })}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              className="btn-primary px-10 py-3 text-base tracking-[0.15em] uppercase"
              disabled={!canSpin || spin.isPending || spinning}
              onClick={doSpin}
            >
              {spin.isPending ? 'Opening...' : 'Spin'}
            </button>
            <span className="text-sm text-slate-400">
              {run.options_per_player} options each · {run.alive_count} champions alive
            </span>
          </div>
          <ErrorText error={spin.error} />
          {spin.error && run.tokens_available === 0 && run.alive_count < chosen.length && (
            <EndRunButton run={run} />
          )}
        </section>
      )}

      {spinning && (
        <section className="card flex flex-col gap-4" aria-live="polite">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-bold text-gold-100">Opening...</h2>
            <button className="btn-secondary px-3 py-1.5 text-xs" onClick={() => setStage((s) => (s ? { ...s, skipped: true } : s))}>
              Skip
            </button>
          </div>
          {stage.reels.map((r, i) => (
            <CaseReel
              key={`${stage.key}-${r.playerId}`}
              label={playerMap.get(r.playerId)?.display_name ?? `Player ${r.playerId}`}
              strip={r.strip}
              championMap={champs}
              startAt={stage.startAt}
              durationMs={SPIN_MS}
              offset={r.offset}
              master={i === 0}
              skipped={stage.skipped}
              onDone={i === 0 ? finishSpin : undefined}
            />
          ))}
        </section>
      )}

      {shownAssignments && !spinning && (
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {shownAssignments.map((a, i) => (
            <div key={`${stage?.key}-${a.player_id}`} className="reel-land" style={{ animationDelay: `${i * 70}ms` }}>
              <PlayerCard assignment={a} game={pending ? pendingGame.data! : null} />
            </div>
          ))}
        </section>
      )}

      {pending && pendingGame.data && !spinning && (
        <PendingGamePanel game={pendingGame.data} onResolved={(g) => setLastResolvedId(g.id)} />
      )}
      {!pending && lastResolvedId != null && <LastResult gameId={lastResolvedId} />}
    </div>
  )
}

function PlayerCard({ assignment, game }: { assignment: Assignment; game: Game | null }) {
  const champs = useChampionMap()
  const playerMap = usePlayerMap()
  const [pickingOther, setPickingOther] = useState(false)
  const setPick = useAction((pick: { option_index?: number; champion_id?: string }) =>
    api.setPicks(game!.id, [{ player_id: assignment.player_id, ...pick }]),
  )
  const player = playerMap.get(assignment.player_id)
  const [first, ...backups] = assignment.options
  const isOther = assignment.played_champion_id != null && assignment.played_option_index == null

  return (
    <div className="card flex h-full flex-col gap-3">
      <h3 className="font-display font-bold text-gold-100">{player?.display_name ?? `Player ${assignment.player_id}`}</h3>
      <ol className="flex flex-col gap-1.5">
        {[first, ...backups].map((cid, idx) => {
          const played = assignment.played_option_index === idx
          return (
            <li key={cid} className="reel-land" style={{ animationDelay: `${idx * 80}ms` }}>
              <button
                disabled={!game || setPick.isPending}
                onClick={() => setPick.mutate({ option_index: idx })}
                aria-pressed={played}
                className={`flex w-full items-center gap-3 rounded-2xl p-1.5 text-left transition duration-150 active:scale-[0.98] ${
                  played ? 'bg-gold-500/15 ring-2 ring-gold-400 ring-inset' : game ? 'hover:bg-white/5' : ''
                }`}
              >
                <span className="w-5 text-center text-sm font-bold text-slate-400">{idx + 1}</span>
                <ChampionPortrait
                  champion={champs.get(cid)}
                  size={idx === 0 ? 'mdlg' : 'sm'}
                  className={idx === 0 ? 'land-glow rounded-xl' : 'rounded-lg'}
                />
                <span className={idx === 0 ? 'text-lg font-semibold' : 'text-sm'}>{champs.get(cid)?.name ?? cid}</span>
                {played && <span className="ml-auto text-xs font-bold uppercase text-gold-300">Played</span>}
              </button>
            </li>
          )
        })}
      </ol>
      {game && (
        <div className="flex items-center gap-2 border-t border-slate-800 pt-2 text-sm">
          {isOther ? (
            <>
              <ChampionPortrait champion={champs.get(assignment.played_champion_id!)} size="xs" />
              <span>
                Played <b>{champs.get(assignment.played_champion_id!)?.name}</b> (other)
              </span>
            </>
          ) : (
            <span className="text-slate-400">{assignment.played_champion_id ? '' : 'Tap the one they played.'}</span>
          )}
          <button className="ml-auto text-xs text-slate-400 underline hover:text-slate-200" onClick={() => setPickingOther(true)}>
            Other...
          </button>
        </div>
      )}
      <ErrorText error={setPick.error} />
      {pickingOther && <OtherPicker onClose={() => setPickingOther(false)} onPick={(c) => setPick.mutate({ champion_id: c.id }, { onSuccess: () => setPickingOther(false) })} />}
    </div>
  )
}

function OtherPicker({ onClose, onPick }: { onClose: () => void; onPick: (c: Champion) => void }) {
  const { data } = useChampions()
  return (
    <Modal title="Which champion did they play?" onClose={onClose}>
      <ChampionPicker champions={data ?? []} onPick={onPick} />
    </Modal>
  )
}

function PendingGamePanel({ game, onResolved }: { game: Game; onResolved: (g: Game) => void }) {
  const result = useAction(({ result, reason }: { result: 'win' | 'loss' | 'void'; reason?: string }) =>
    api.setResult(game.id, result, reason),
  )
  const allMarked = game.assignments.every((a) => a.played_champion_id)
  const submit = (r: 'win' | 'loss' | 'void', reason?: string) => result.mutate({ result: r, reason }, { onSuccess: onResolved })
  const resultButtons = (
    <>
      <button className="btn-success px-5 sm:px-6" disabled={result.isPending} onClick={() => submit('win')}>
        Win
      </button>
      <button
        className="btn-danger px-5 sm:px-6"
        disabled={result.isPending || !allMarked}
        title={allMarked ? undefined : 'Mark everyone first'}
        onClick={() => submit('loss')}
      >
        Loss
      </button>
      <button className="btn-secondary" disabled={result.isPending} onClick={() => submit('void', 'remake / manual void')}>
        Void
      </button>
    </>
  )

  return (
    <section className="card flex flex-col gap-3 border-gold-600/40">
      <h2 className="font-semibold">
        Game {game.id} · {game.needs_review ? 'check this one' : 'waiting on the result'}
      </h2>
      {game.needs_review ? <ReviewPanel game={game} onResolved={onResolved} /> : <AutoStatus game={game} />}
      {!allMarked && !game.needs_review && (
        <p className="text-sm text-slate-400">
          Entering it yourself? Tap what everyone played. On a win, anyone you skip counts as their first pick. For a
          loss, mark everyone.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <div className="hidden gap-2 sm:flex">{resultButtons}</div>
        <button
          className="btn-secondary sm:ml-auto"
          disabled={result.isPending}
          onClick={() => confirm('Throw out this spin and re-roll?') && submit('void', 're-roll')}
        >
          Void spin (re-roll)
        </button>
      </div>
      <ErrorText error={result.error} />
      {/* Phones: keep the result buttons in reach without scrolling past every player's card */}
      <div className="h-16 sm:hidden" aria-hidden />
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-800 bg-[#020b16]/97 px-4 py-3 sm:hidden">
        <div className="mx-auto flex max-w-6xl items-center gap-2">
          <span className="mr-auto text-xs text-slate-400">Game #{game.id}</span>
          {resultButtons}
        </div>
      </div>
    </section>
  )
}

/** Explains whether the Riot auto-matcher is watching this game, with a "Check now" button. */
function AutoStatus({ game }: { game: Game }) {
  const riot = useRiotStatus()
  const { settings } = useActiveRun()
  const playerMap = usePlayerMap()
  const sync = useAction(api.sync)
  const unlinked = game.assignments
    .map((a) => playerMap.get(a.player_id))
    .filter((p) => p && !p.puuid)
    .map((p) => p!.display_name)

  let text: string
  let watching = false
  if (!riot.data?.key_set) text = 'No Riot key set up, so enter the result yourself below.'
  else if (!settings.data?.challenge_mode) text = "Challenge mode is off, so this game won't be picked up from Riot."
  else if (unlinked.length) text = `To get results from Riot, everyone needs a linked Riot ID. Missing: ${unlinked.join(', ')}.`
  else {
    watching = true
    const secs = settings.data?.poll_interval_seconds ?? 90
    text = `Waiting for the game to end. We check Riot every ${secs} seconds and fill in the result for you.`
  }
  const outcome = sync.data?.games.find((g) => g.game_id === game.id)

  return (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        {watching && <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />}
        <span className="text-slate-300">{text}</span>
        {watching && (
          <button className="text-xs underline" disabled={sync.isPending} onClick={() => sync.mutate(undefined)}>
            {sync.isPending ? 'Checking...' : 'Check now'}
          </button>
        )}
      </div>
      {outcome?.status === 'waiting' && <p className="text-xs text-slate-500">Nothing yet.</p>}
      {sync.data && sync.data.errors.length > 0 && <p className="text-xs text-red-300">{sync.data.errors.join('; ')}</p>}
      <ErrorText error={sync.error} />
    </div>
  )
}

function ReviewPanel({ game, onResolved }: { game: Game; onResolved: (g: Game) => void }) {
  const review = useAction((action: 'accept' | 'reject') => api.review(game.id, action))
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
      <p className="text-sm text-amber-200">Found the game, but something looks off: {game.review_reason}</p>
      {game.match && <MatchSummaryView match={game.match} flagOptions />}
      <div className="flex flex-wrap gap-2">
        <button
          className="btn-primary"
          disabled={review.isPending}
          onClick={() => review.mutate('accept', { onSuccess: onResolved })}
        >
          Use it anyway
        </button>
        <button className="btn-secondary" disabled={review.isPending} onClick={() => review.mutate('reject')}>
          Wrong game
        </button>
      </div>
      <p className="text-xs text-slate-400">Or just enter the result below.</p>
      <ErrorText error={review.error} />
    </div>
  )
}

function LastResult({ gameId }: { gameId: number }) {
  const { data: game } = useGame(gameId)
  const champs = useChampionMap()
  const playerMap = usePlayerMap()
  const undo = useAction(() => api.undo(gameId))
  if (!game || game.status === 'pending') return null

  const tone = { won: 'text-emerald-300', lost: 'text-red-300', void: 'text-slate-300', pending: '' }[game.status]
  const label = { won: 'Win!', lost: 'Loss', void: 'Thrown out', pending: '' }[game.status]
  return (
    <section className="card flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className={`text-xl font-bold ${tone}`}>
          {label}
          {game.result_source === 'auto' && (
            <span className="ml-2 rounded bg-sky-500/15 px-2 py-0.5 align-middle text-xs font-medium text-sky-300">
              from Riot{game.void_reason === 'remake' ? ' (remake)' : ''}
            </span>
          )}
        </h2>
        <button className="btn-secondary" disabled={undo.isPending} onClick={() => undo.mutate(undefined)}>
          Undo
        </button>
      </div>
      {game.eliminated.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-slate-400">Eliminated:</span>
          {game.eliminated.map((cid) => (
            <span key={cid} className="flex items-center gap-1.5 rounded bg-red-950/50 px-2 py-1">
              <ChampionPortrait champion={champs.get(cid)} size="xs" dim />
              {champs.get(cid)?.name}
            </span>
          ))}
        </div>
      )}
      {game.match && <MatchSummaryView match={game.match} />}
      {game.tokens_earned.length > 0 && (
        <p className="text-sm text-gold-300">
          3 in a row! Revive token for {game.tokens_earned.map((p) => playerMap.get(p)?.display_name).join(', ')}.
        </p>
      )}
      <ErrorText error={undo.error} />
    </section>
  )
}

function EndRunButton({ run }: { run: Run }) {
  const end = useAction(() => api.endRun(run.id))
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-slate-400">Not enough champs left, and no tokens to bring any back.</span>
      <button className="btn-danger" onClick={() => confirm(`End "${run.name}" with ${run.win_count} wins?`) && end.mutate(undefined)}>
        End run
      </button>
    </div>
  )
}
