import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ChampionPicker } from '../components/ChampionPicker'
import { MatchSummaryView } from '../components/MatchSummary'
import { SlotReel } from '../components/SlotReel'
import { ChampionPortrait, EmptyState, ErrorText, Modal } from '../components/ui'
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
import type { Assignment, Champion, Game, Run } from '../types'

const BASE_SPIN_MS = 1800
const STAGGER_MS = 350

export function WheelsPage() {
  const { settings, run, runId } = useActiveRun()

  if (settings.isLoading || run.isLoading) return <p className="text-slate-400">Loading...</p>
  if (!runId || !run.data) {
    return (
      <EmptyState title="No active run">
        <p className="text-sm text-slate-400">Add your players and start a run to begin spinning.</p>
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
  const [selected, setSelected] = useState<number[] | null>(null)
  const [practice, setPractice] = useState<Assignment[] | null>(null)
  const [animating, setAnimating] = useState<{ key: number; landed: Set<number> } | null>(null)
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

  const chosen = selected ?? []
  const toggle = (id: number) =>
    setSelected(chosen.includes(id) ? chosen.filter((p) => p !== id) : chosen.length < 5 ? [...chosen, id] : chosen)

  const pending = run.pending_game_id != null
  const canSpin = run.status === 'active' && !pending && chosen.length >= 2 && chosen.length <= 5

  const doSpin = () =>
    spin.mutate(chosen, {
      onSuccess: (res) => {
        setPractice(res.practice ? res.assignments : null)
        setLastResolvedId(null)
        setAnimating({ key: Date.now(), landed: new Set() })
      },
    })

  const shownAssignments = pending ? pendingGame.data?.assignments : practice ?? undefined
  const allLanded = !animating || (shownAssignments ?? []).every((a) => animating.landed.has(a.player_id))
  const markLanded = (pid: number) =>
    setAnimating((a) => (a ? { ...a, landed: new Set(a.landed).add(pid) } : a))

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
        <p className="rounded-md bg-red-950/60 px-3 py-2 text-sm text-red-200">
          This run has ended with <b>{run.win_count}</b> wins. Start a new one in Settings.
        </p>
      )}

      {!pending && (
        <section className="card flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">
              Who's playing? <span className="text-sm font-normal text-slate-400">({chosen.length}/5, need 2+)</span>
            </h2>
            {!challengeMode && (
              <span className="rounded bg-slate-700 px-2 py-0.5 text-xs uppercase tracking-wide">Practice spin</span>
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
                  className={`rounded-full px-3 py-1.5 text-sm ring-1 transition ${
                    on ? 'bg-gold-500 text-slate-950 ring-gold-400' : 'bg-slate-800 ring-slate-700 hover:bg-slate-700'
                  }`}
                >
                  {p.display_name}
                </button>
              )
            })}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button className="btn-primary px-8 py-2.5 text-base" disabled={!canSpin || spin.isPending} onClick={doSpin}>
              {spin.isPending ? 'Spinning...' : 'Spin'}
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

      {shownAssignments && (
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {shownAssignments.map((a, i) => (
            <PlayerCard
              key={`${animating?.key}-${a.player_id}`}
              assignment={a}
              game={pending ? pendingGame.data! : null}
              reel={
                animating && !animating.landed.has(a.player_id)
                  ? { pool: alivePool, durationMs: BASE_SPIN_MS + i * STAGGER_MS, onLanded: () => markLanded(a.player_id) }
                  : null
              }
            />
          ))}
        </section>
      )}

      {pending && pendingGame.data && allLanded && (
        <PendingGamePanel game={pendingGame.data} onResolved={(g) => setLastResolvedId(g.id)} />
      )}
      {!pending && lastResolvedId != null && <LastResult gameId={lastResolvedId} />}
    </div>
  )
}

function PlayerCard({
  assignment,
  game,
  reel,
}: {
  assignment: Assignment
  game: Game | null
  reel: { pool: string[]; durationMs: number; onLanded: () => void } | null
}) {
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
    <div className="card flex flex-col gap-3">
      <h3 className="font-semibold">{player?.display_name ?? `Player ${assignment.player_id}`}</h3>
      {reel ? (
        <div className="flex items-center gap-3">
          <SlotReel
            pool={reel.pool.length ? reel.pool : assignment.options}
            finalId={first}
            championMap={champs}
            durationMs={reel.durationMs}
            onLanded={reel.onLanded}
          />
          <span className="text-sm text-slate-400">Spinning...</span>
        </div>
      ) : (
        <ol className="flex flex-col gap-1.5">
          {[first, ...backups].map((cid, idx) => {
            const played = assignment.played_option_index === idx
            return (
              <li key={cid} className="reel-land" style={{ animationDelay: `${idx * 80}ms` }}>
                <button
                  disabled={!game || setPick.isPending}
                  onClick={() => setPick.mutate({ option_index: idx })}
                  className={`flex w-full items-center gap-3 rounded-lg p-1.5 text-left transition ${
                    played ? 'bg-gold-500/20 ring-2 ring-gold-400' : game ? 'hover:bg-slate-800' : ''
                  }`}
                >
                  <span className="w-5 text-center text-sm font-bold text-slate-400">{idx + 1}</span>
                  <ChampionPortrait champion={champs.get(cid)} size={idx === 0 ? 'lg' : 'sm'} />
                  <span className={idx === 0 ? 'text-lg font-semibold' : 'text-sm'}>{champs.get(cid)?.name ?? cid}</span>
                  {played && <span className="ml-auto text-xs font-bold uppercase text-gold-300">Played</span>}
                </button>
              </li>
            )
          })}
        </ol>
      )}
      {game && !reel && (
        <div className="flex items-center gap-2 border-t border-slate-800 pt-2 text-sm">
          {isOther ? (
            <>
              <ChampionPortrait champion={champs.get(assignment.played_champion_id!)} size="xs" />
              <span>
                Played <b>{champs.get(assignment.played_champion_id!)?.name}</b> (other)
              </span>
            </>
          ) : (
            <span className="text-slate-400">{assignment.played_champion_id ? '' : 'Click the champion they played.'}</span>
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

  return (
    <section className="card flex flex-col gap-3 border-gold-600/40">
      <h2 className="font-semibold">
        Game #{game.id}: {game.needs_review ? 'needs review' : 'waiting for result'}
      </h2>
      {game.needs_review ? <ReviewPanel game={game} onResolved={onResolved} /> : <AutoStatus game={game} />}
      {!allMarked && !game.needs_review && (
        <p className="text-sm text-slate-400">
          Recording by hand? Click the champion each player played. On a win, anyone left unmarked counts as option 1.
          A loss needs everyone marked.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button className="btn-success px-6" disabled={result.isPending} onClick={() => submit('win')}>
          Win
        </button>
        <button className="btn-danger px-6" disabled={result.isPending || !allMarked} onClick={() => submit('loss')}>
          Loss
        </button>
        <button className="btn-secondary" disabled={result.isPending} onClick={() => submit('void', 'remake / manual void')}>
          Void (remake)
        </button>
        <button
          className="btn-secondary ml-auto"
          disabled={result.isPending}
          onClick={() => confirm('Void this spin and re-roll? This is logged.') && submit('void', 're-roll')}
        >
          Void spin (re-roll)
        </button>
      </div>
      <ErrorText error={result.error} />
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
  if (!riot.data?.key_set) text = 'No Riot API key, so record the result by hand below.'
  else if (!settings.data?.challenge_mode) text = 'Challenge mode is off, so this game will not be auto-matched.'
  else if (unlinked.length) text = `Auto results need every player linked to Riot. Not linked: ${unlinked.join(', ')}.`
  else {
    watching = true
    const secs = settings.data?.poll_interval_seconds ?? 90
    text = `Waiting for the match to finish. Checking Riot every ${secs} seconds; the result applies automatically.`
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
      {outcome?.status === 'waiting' && <p className="text-xs text-slate-500">No finished match found yet.</p>}
      {sync.data && sync.data.errors.length > 0 && <p className="text-xs text-red-300">{sync.data.errors.join('; ')}</p>}
      <ErrorText error={sync.error} />
    </div>
  )
}

function ReviewPanel({ game, onResolved }: { game: Game; onResolved: (g: Game) => void }) {
  const review = useAction((action: 'accept' | 'reject') => api.review(game.id, action))
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
      <p className="text-sm text-amber-200">Found a match, but it didn't pass every check: {game.review_reason}</p>
      {game.match && <MatchSummaryView match={game.match} flagOptions />}
      <div className="flex flex-wrap gap-2">
        <button
          className="btn-primary"
          disabled={review.isPending}
          onClick={() => review.mutate('accept', { onSuccess: onResolved })}
        >
          Use this match anyway
        </button>
        <button className="btn-secondary" disabled={review.isPending} onClick={() => review.mutate('reject')}>
          Not this game, keep looking
        </button>
      </div>
      <p className="text-xs text-slate-400">Or record the result by hand with the buttons below.</p>
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
  const label = { won: 'Victory!', lost: 'Defeat', void: 'Voided', pending: '' }[game.status]
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
          3-win streak! Revive token earned by {game.tokens_earned.map((p) => playerMap.get(p)?.display_name).join(', ')}.
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
      <span className="text-slate-400">Not enough champions left and no tokens.</span>
      <button className="btn-danger" onClick={() => confirm(`End "${run.name}" with ${run.win_count} wins?`) && end.mutate(undefined)}>
        End run
      </button>
    </div>
  )
}
