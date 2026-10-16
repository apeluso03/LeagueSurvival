import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { ChampionPicker } from '../components/ChampionPicker'
import { MatchSummaryView } from '../components/MatchSummary'
import { CaseReel } from '../components/CaseReel'
import { ContractReveal } from '../components/ContractReveal'
import { BanStrip, BuildStrip, RoleChip } from '../components/BuildStrip'
import { DangerMeter } from '../components/DangerMeter'
import { SurvivalOdds } from '../components/SurvivalOdds'
import { LoadingScreen, LockInMoment } from '../components/LockIn'
import { LowerThird } from '../components/LowerThird'
import { PickBar } from '../components/PickBar'
import { GoldBadge } from '../components/Gold'
import { BlacklistDialog, PickChampionDialog, SwapDialog } from '../components/ItemDialogs'
import { ShieldIcon } from '../components/icons'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState, Modal } from '../components/ui'
import {
  useAction,
  useActiveRun,
  useChampionMap,
  useChampions,
  useGame,
  useLive,
  usePlayerMap,
  usePlayers,
  useEconomy,
  useComp,
  useOptionFacts,
  usePool,
  useRiotStatus,
  useShop,
} from '../hooks/queries'
import { useAccess } from '../hooks/useAuth'
import { useBuy, useOwnedItem } from '../hooks/useItems'
import { factLine } from '../lib/facts'
import { teamColor } from '../lib/teams'
import { ITEM_META, ITEM_ORDER } from '../lib/items'
import { preloadImages } from '../lib/preload'
import { SPIN_MS, buildStrip, randomLandingOffset } from '../lib/reel'
import { playLand, playReveal, playStart, unlock } from '../lib/sound'
import type { Assignment, Champion, CompPick, ContractInfo, Game, ItemType, PlayerEconomy, Run } from '../types'

// Reels stop one after another: the first after 9.5s, then each next one this much later
// (11.9s for a full five-player spin).
const STAGGER_MS = 600
// Players who don't run the wheels check this often for a new spin (live updates come later).
const WATCH_MS = 10_000
const reelMs = (i: number) => SPIN_MS - 1000 + i * STAGGER_MS

type SpinStage = {
  key: number
  startAt: number // identifies this spin; the reels start together on their first painted frame
  reels: { playerId: number; strip: string[]; offset: number; options: number }[]
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
  const [lockIn, setLockIn] = useState<Game | null>(null)
  const [editPicks, setEditPicks] = useState(false)
  const qc = useQueryClient()
  const { canManage, myPlayerId } = useAccess(run)
  useQuery({ queryKey: ['run', run.id], queryFn: () => api.run(run.id), enabled: !canManage, refetchInterval: WATCH_MS })
  // Not useAction: refreshing every query (and re-rendering the page) right as the reels start made
  // the first frames stutter. The pending game goes straight into the cache instead, and everything
  // else refreshes once the spin is over.
  const spin = useMutation({ mutationFn: (ids: number[]) => api.spin(run.id, ids) })
  const refreshAll = () => void qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'champions' })

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

  // Everyone just finished picking: play the lock-in and switch to the loading-screen view.
  const game = pendingGame.data?.status === 'pending' ? pendingGame.data : undefined
  const allPicked = !!game && game.assignments.every((a) => a.played_champion_id)
  const picked = useRef<{ id: number; all: boolean } | null>(null)
  useEffect(() => {
    if (!game) return
    const prev = picked.current
    picked.current = { id: game.id, all: allPicked }
    if (prev?.id !== game.id) setEditPicks(false)
    else if (!prev.all && allPicked) {
      setLockIn(game)
      setEditPicks(false)
    }
  }, [game, allPicked])

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
        const game = res.game
        if (game) {
          qc.setQueryData(['game', game.id], game)
          qc.setQueryData<Run>(['run', run.id], (r) => (r ? { ...r, pending_game_id: game.id } : r))
        }
        // Skip the reels for people who asked their device for reduced motion.
        const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
        if (reduced) {
          refreshAll()
          return setStage(null)
        }
        const fillers = alivePool.length ? alivePool : res.assignments.flatMap((a) => a.options)
        setStage({
          key: Date.now(),
          startAt: performance.now(),
          reels: res.assignments.map((a) => ({
            playerId: a.player_id,
            strip: buildStrip(fillers, a.options),
            offset: randomLandingOffset(),
            options: a.options.length,
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
    if (stage?.skipped) playReveal() // otherwise the last reel already chimed as it landed
    const hold = stage?.skipped ? 500 : 1300
    const key = stage?.key
    refreshAll()
    setTimeout(() => setStage((s) => (s && s.key === key ? { ...s, done: true } : s)), hold)
  }

  const shownAssignments = pending ? pendingGame.data?.assignments : practice ?? undefined
  // High-elo builds for each player's pick (or their #1 option until they pick), shown in the cards.
  const compIds = useMemo(() => (shownAssignments ?? []).map((a) => a.played_champion_id ?? a.options[0]), [shownAssignments])
  // Bans skip every option on the board, so nobody's backup gets banned away.
  const allOptions = useMemo(() => [...new Set((shownAssignments ?? []).flatMap((a) => a.options))].sort(), [shownAssignments])
  const comp = useComp(compIds, allOptions)
  const builds = useMemo(() => new Map((comp.data?.picks ?? []).map((p) => [p.champion_id, p])), [comp.data])

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

      {!pending && !spinning && !canManage && (
        <WaitingForSpin run={run} challengeMode={challengeMode} myPlayerId={myPlayerId} players={Math.max(2, lastUsed.length)} />
      )}

      {!pending && !spinning && canManage && (
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
                  className={`team-chip ${on ? 'is-on' : ''}`}
                  style={{ ['--team' as string]: teamColor(p.id) } as CSSProperties}
                >
                  {p.display_name}
                </button>
              )
            })}
          </div>
          {challengeMode && chosen.length > 0 && run.status === 'active' && <PrepRow run={run} playerIds={chosen} />}
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
          {challengeMode && run.status === 'active' && (
            <DangerMeter
              alive={run.alive_count}
              total={run.total_count}
              players={chosen.length >= 2 ? chosen.length : Math.max(2, lastUsed.length)}
              options={run.options_per_player}
              tokens={run.tokens_available}
            />
          )}
          {challengeMode && run.status === 'active' && (
            <SurvivalOdds run={run} players={chosen.length >= 2 ? chosen.length : Math.max(2, lastUsed.length)} />
          )}
          <ErrorText error={spin.error} />
          {spin.error && run.tokens_available === 0 && run.alive_count < chosen.length && (
            <EndRunButton run={run} />
          )}
        </section>
      )}

      {spinning && (
        <section className="card flex flex-col gap-4" aria-live="polite">
          <div className="flex flex-wrap items-center gap-3">
            <span className="broadcast-tag" style={{ ['--tag' as string]: '#e5283c' } as CSSProperties}>
              <span className="live-dot" /> Live
            </span>
            <h2 className="text-lg text-white">
              Draft <span className="text-hex-300">·</span> Pick phase
            </h2>
            <button className="btn-secondary ml-auto px-3 py-1.5 text-xs" onClick={() => setStage((s) => (s ? { ...s, skipped: true } : s))}>
              Skip
            </button>
          </div>
          {!stage.skipped && (
            <div className="draft-timer" aria-hidden>
              <span key={stage.key} style={{ animationDuration: `${reelMs(stage.reels.length - 1)}ms` }} />
            </div>
          )}
          {stage.reels.map((r, i) => {
            const last = i === stage.reels.length - 1
            return (
              <CaseReel
                key={`${stage.key}-${r.playerId}`}
                label={playerMap.get(r.playerId)?.display_name ?? `Player ${r.playerId}`}
                strip={r.strip}
                championMap={champs}
                startAt={stage.startAt}
                durationMs={reelMs(i)}
                offset={r.offset}
                master={last}
                skipped={stage.skipped}
                onLand={() => (last ? playReveal() : playLand(i))}
                onDone={last ? finishSpin : undefined}
                team={teamColor(r.playerId)}
                optionCount={r.options}
              />
            )
          })}
        </section>
      )}

      {game && !spinning && <PickBar game={game} extra={<BanStrip bans={comp.data?.bans} loading={comp.isLoading} />} />}
      {!game && practice && !spinning && (
        <div className="flex justify-end">
          <BanStrip bans={comp.data?.bans} loading={comp.isLoading} />
        </div>
      )}

      {game && allPicked && !editPicks && !spinning ? (
        <LoadingScreen game={game} onEdit={canManage ? () => setEditPicks(true) : undefined} builds={builds} />
      ) : (
        shownAssignments &&
        !spinning && (
          <section className="flex flex-col gap-2">
            {/* One row of cards on desktop, so picks, builds and the result buttons fit on one screen. */}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[repeat(auto-fit,minmax(220px,1fr))]">
              {shownAssignments.map((a, i) => (
                <div key={`${stage?.key}-${a.player_id}`} className="reel-land" style={{ animationDelay: `${i * 70}ms` }}>
                  <PlayerCard
                    assignment={a}
                    game={pending ? pendingGame.data! : null}
                    build={builds.get(a.played_champion_id ?? a.options[0])}
                    buildLoading={comp.isLoading}
                  />
                </div>
              ))}
            </div>
            {game && allPicked && (
              <button className="btn-secondary self-start" onClick={() => setEditPicks(false)}>
                Done changing picks
              </button>
            )}
          </section>
        )
      )}
      {lockIn && <LockInMoment key={lockIn.id} game={lockIn} onDone={() => setLockIn(null)} />}

      {pending && pendingGame.data && !spinning && (
        <PendingGamePanel game={pendingGame.data} onResolved={(g) => setLastResolvedId(g.id)} />
      )}
      {!pending && lastResolvedId != null && <LastResult gameId={lastResolvedId} />}
    </div>
  )
}

function PlayerCard({
  assignment,
  game,
  build,
  buildLoading,
}: {
  assignment: Assignment
  game: Game | null
  build: CompPick | undefined
  buildLoading: boolean
}) {
  const champs = useChampionMap()
  const playerMap = usePlayerMap()
  const [pickingOther, setPickingOther] = useState(false)
  const [replay, setReplay] = useState<{ key: number; startAt: number; strip: string[]; offset: number; options: number } | null>(null)
  const pool = usePool(game?.run_id)
  const facts = useOptionFacts(game?.id).data?.[String(assignment.player_id)]
  const shielded = useMemo(
    () => new Set((pool.data ?? []).filter((e) => e.shield_item_id).map((e) => e.champion_id)),
    [pool.data],
  )
  const onRerolled = (newOptions: string[]) => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduced) return
    const alive = (pool.data ?? []).filter((e) => e.status === 'alive').map((e) => e.champion_id)
    setReplay({
      key: Date.now(),
      startAt: performance.now() + 150,
      strip: buildStrip(alive.length ? alive : newOptions, newOptions),
      offset: randomLandingOffset(),
      options: newOptions.length,
    })
    playStart()
  }
  const setPick = useAction((pick: { option_index?: number; champion_id?: string }) =>
    api.setPicks(game!.id, [{ player_id: assignment.player_id, ...pick }]),
  )
  const { canManage, canActFor } = useAccess()
  const canPick = !!game && canManage
  const player = playerMap.get(assignment.player_id)
  const [first, ...backups] = assignment.options
  const isOther = assignment.played_champion_id != null && assignment.played_option_index == null

  return (
    <div className="card flex h-full flex-col gap-2.5 p-3.5">
      <div className="flex items-center gap-2">
        <h3 className="min-w-0">
          {/* Picked / picking shows in the pick bar and on the option itself, so the name gets the room. */}
          <LowerThird playerId={assignment.player_id} name={player?.display_name} size="sm" />
        </h3>
        <RoleChip pick={build} />
        {canPick && (
          <button className="ml-auto shrink-0 text-[11px] text-slate-400 underline hover:text-slate-200" onClick={() => setPickingOther(true)}>
            Other...
          </button>
        )}
      </div>
      {replay ? (
        <CaseReel
          key={replay.key}
          label="Rerolling..."
          strip={replay.strip}
          championMap={champs}
          startAt={replay.startAt}
          durationMs={SPIN_MS - 2500}
          offset={replay.offset}
          optionCount={replay.options}
          master
          skipped={false}
          onDone={() => {
            playReveal()
            setTimeout(() => setReplay(null), 900)
          }}
        />
      ) : (
      <ol className="flex flex-col gap-1">
        {[first, ...backups].map((cid, idx) => {
          const played = assignment.played_option_index === idx
          return (
            <li key={cid} className="reel-land" style={{ animationDelay: `${idx * 80}ms` }}>
              <button
                disabled={!canPick || setPick.isPending}
                onClick={() => setPick.mutate({ option_index: idx })}
                aria-pressed={played}
                className={`flex w-full items-center gap-2 rounded-sm p-1 text-left transition duration-150 enabled:active:scale-[0.98] ${
                  played ? 'bg-gold-500/15 ring-2 ring-gold-400 ring-inset' : canPick ? 'hover:bg-white/5' : ''
                }`}
              >
                <span className="w-3 text-center text-xs font-bold text-slate-500">{idx + 1}</span>
                <ChampionPortrait
                  champion={champs.get(cid)}
                  size={idx === 0 ? 'md' : 'xs'}
                  className={idx === 0 ? 'land-glow rounded-sm' : 'rounded-sm'}
                />
                <span className="flex min-w-0 flex-col">
                  <span className={`truncate ${idx === 0 ? 'text-base font-semibold' : 'text-sm'}`}>{champs.get(cid)?.name ?? cid}</span>
                  {facts?.[cid] && (
                    <span className="truncate text-[10px] leading-snug text-slate-400" title={factLine(facts[cid])}>
                      {factLine(facts[cid])}
                    </span>
                  )}
                </span>
                {shielded.has(cid) && (
                  <span title="Shielded: a loss won't eliminate it" className="text-emerald-300">
                    <ShieldIcon className="h-4 w-4" />
                  </span>
                )}
                {played && <span className="ml-auto text-[10px] font-bold uppercase text-gold-300">Played</span>}
              </button>
            </li>
          )
        })}
      </ol>
      )}
      {isOther && (
        <div className="flex items-center gap-2 text-xs">
          <ChampionPortrait champion={champs.get(assignment.played_champion_id!)} size="xs" />
          <span>
            Played <b>{champs.get(assignment.played_champion_id!)?.name}</b> (other)
          </span>
        </div>
      )}
      <div className="border-t border-white/[0.07] pt-2">
        <BuildStrip pick={build} loading={buildLoading} />
      </div>
      {game && game.status === 'pending' && !assignment.played_champion_id && !replay && canActFor(assignment.player_id) && (
        <SpinItems game={game} assignment={assignment} onRerolled={onRerolled} />
      )}
      <ErrorText error={setPick.error} />
      {pickingOther && <OtherPicker onClose={() => setPickingOther(false)} onPick={(c) => setPick.mutate({ champion_id: c.id }, { onSuccess: () => setPickingOther(false) })} />}
    </div>
  )
}

/** Gold, armed Blacklist and Contract for each player about to spin (SPEC 10.1). */
function PrepRow({ run, playerIds }: { run: Run; playerIds: number[] }) {
  const economy = useEconomy(run.id)
  const playerMap = usePlayerMap()
  const champs = useChampionMap()
  const shop = useShop(run.id)
  const pool = usePool(run.id)
  const buy = useBuy(run.id)
  const owned = useOwnedItem(run.id)
  const [blacklistFor, setBlacklistFor] = useState<number | null>(null)
  const [revealed, setRevealed] = useState<{ contract: ContractInfo; name?: string } | null>(null)
  const price = (t: ItemType) => shop.data?.config.prices[t] ?? 0
  const byId = new Map((economy.data ?? []).map((e) => [e.player_id, e]))
  const alive = (pool.data ?? []).filter((e) => e.status === 'alive')

  const armBlacklist = async (pid: number, econ: PlayerEconomy | undefined) => {
    if (!econ?.unused.blacklist) await buy.mutateAsync({ playerId: pid, type: 'blacklist' })
    setBlacklistFor(pid)
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {playerIds.map((pid) => {
          const econ = byId.get(pid)
          const name = playerMap.get(pid)?.display_name
          const hasBl = (econ?.unused.blacklist ?? 0) > 0
          return (
            <div key={pid} className="flex flex-col gap-2 rounded-sm bg-white/[0.03] p-3 ring-1 ring-white/5 ring-inset">
              <div className="flex items-center justify-between gap-2">
                <LowerThird playerId={pid} name={name} size="sm" />
                <GoldBadge amount={econ?.balance ?? 0} />
              </div>
              {econ?.armed_blacklist && (
                <div className="text-xs text-red-200">
                  Banned next spin: {econ.armed_blacklist.map((c) => champs.get(c)?.name ?? c).join(', ')}
                </div>
              )}
              {econ?.active_contract && <div className="text-xs text-gold-200">Contract: {econ.active_contract.description}</div>}
              <OwnedItems econ={econ} />
              <div className="flex flex-wrap gap-1.5">
                {!econ?.armed_blacklist && (
                  <button
                    className="btn-secondary px-2.5 py-1 text-xs"
                    disabled={buy.isPending || (!hasBl && (econ?.balance ?? 0) < price('blacklist'))}
                    onClick={() => void armBlacklist(pid, econ).catch(() => {})}
                  >
                    <ITEM_META.blacklist.Icon className="h-3.5 w-3.5" />
                    {hasBl ? 'Blacklist' : `Blacklist · ${price('blacklist')}g`}
                  </button>
                )}
                <button
                  className="btn-secondary px-2.5 py-1 text-xs"
                  disabled={buy.isPending || (econ?.balance ?? 0) < price('contract')}
                  onClick={() =>
                    buy.mutate(
                      { playerId: pid, type: 'contract' },
                      { onSuccess: (r) => r.item.contract && setRevealed({ contract: r.item.contract, name }) },
                    )
                  }
                >
                  <ITEM_META.contract.Icon className="h-3.5 w-3.5" />
                  {`Contract · ${price('contract')}g`}
                </button>
              </div>
            </div>
          )
        })}
      </div>
      <ErrorText error={buy.error} />
      {blacklistFor != null && (
        <BlacklistDialog
          champions={alive}
          cap={shop.data?.blacklist_cap ?? 1}
          busy={owned.isPending}
          error={owned.error}
          onClose={() => setBlacklistFor(null)}
          onConfirm={(ids) =>
            owned.mutate(
              { playerId: blacklistFor, type: 'blacklist', body: { champion_ids: ids } },
              { onSuccess: () => setBlacklistFor(null) },
            )
          }
        />
      )}
      {revealed && <ContractReveal contract={revealed.contract} playerName={revealed.name} onClose={() => setRevealed(null)} />}
    </div>
  )
}

/** Unused items a player owns, as a reminder before the spin. */
function OwnedItems({ econ }: { econ: PlayerEconomy | undefined }) {
  const owned = ITEM_ORDER.filter((t) => t !== 'contract' && (econ?.unused[t] ?? 0) > 0)
  if (!owned.length) return null
  const hint: Partial<Record<ItemType, string>> = {
    shield: 'Protect a champion from the Pool tab',
    blacklist: 'Arm it with the Blacklist button to ban champs from your next spin',
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-300">
      <span className="text-slate-500">Has:</span>
      {owned.map((t) => {
        const meta = ITEM_META[t]
        return (
          <span key={t} className="inline-flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5" title={hint[t] ?? 'Use it on your options after the spin'}>
            <meta.Icon className="h-3 w-3" style={{ color: meta.color }} />
            {meta.name} ×{econ!.unused[t]}
          </span>
        )
      })}
      {owned.includes('shield') && (
        <Link to="/pool" className="text-hex-200 underline">
          Place shield
        </Link>
      )}
    </div>
  )
}

/** Reroll / Swap / Choose a Champ for one player after the spin, before lock-in. */
function SpinItems({ game, assignment, onRerolled }: { game: Game; assignment: Assignment; onRerolled: (options: string[]) => void }) {
  const economy = useEconomy(game.run_id)
  const pool = usePool(game.run_id)
  const playerMap = usePlayerMap()
  const owned = useOwnedItem(game.run_id)
  const [dialog, setDialog] = useState<'swap' | 'choose' | null>(null)
  const econ = economy.data?.find((e) => e.player_id === assignment.player_id)
  const others = game.assignments.filter((a) => a.player_id !== assignment.player_id)
  const taken = new Set(others.flatMap((a) => a.options))
  const choosable = (pool.data ?? []).filter((e) => e.status === 'alive' && !taken.has(e.champion_id))

  const button = (type: 'reroll' | 'swap' | 'choose', onClick: () => void) => {
    const n = econ?.unused[type] ?? 0
    const meta = ITEM_META[type]
    return (
      <button
        key={type}
        className={`btn-secondary gap-1 px-2.5 py-1 text-[10px] ${n ? 'item-ready' : ''}`}
        style={n ? ({ ['--c' as string]: meta.color } as CSSProperties) : undefined}
        disabled={!n || owned.isPending}
        title={n ? `${meta.name}: ${n} owned` : `${meta.name}: buy one in the Shop`}
        onClick={onClick}
      >
        <meta.Icon className="h-3.5 w-3.5" style={{ color: n ? meta.color : undefined }} />
        {type === 'choose' ? 'Choose' : meta.name}
        {n > 0 && <span className="text-slate-400">×{n}</span>}
      </button>
    )
  }

  // Items they own pulse (item-ready); the rest stay greyed out with a "buy one" tooltip.
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap gap-1">
        {button('reroll', () =>
          owned.mutate(
            { playerId: assignment.player_id, type: 'reroll', body: { game_id: game.id } },
            { onSuccess: (item) => onRerolled(((item.target.new as string[]) ?? []).filter(Boolean)) },
          ),
        )}
        {button('swap', () => setDialog('swap'))}
        {button('choose', () => setDialog('choose'))}
      </div>
      <ErrorText error={owned.error} />
      {dialog === 'swap' && (
        <SwapDialog
          players={others.map((a) => playerMap.get(a.player_id)!).filter(Boolean)}
          busy={owned.isPending}
          error={owned.error}
          onClose={() => setDialog(null)}
          onPick={(pid) =>
            owned.mutate(
              { playerId: assignment.player_id, type: 'swap', body: { game_id: game.id, other_player_id: pid } },
              { onSuccess: () => setDialog(null) },
            )
          }
        />
      )}
      {dialog === 'choose' && (
        <PickChampionDialog
          title="Choose a champion"
          hint="It becomes this player's only option for the game."
          champions={choosable}
          busy={owned.isPending}
          error={owned.error}
          onClose={() => setDialog(null)}
          onPick={(cid) =>
            owned.mutate(
              { playerId: assignment.player_id, type: 'choose', body: { game_id: game.id, champion_id: cid } },
              { onSuccess: () => setDialog(null) },
            )
          }
        />
      )}
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
  const { canManage } = useAccess()
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
    <section className="card flex flex-col gap-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="broadcast-tag shrink-0" style={{ ['--tag' as string]: game.needs_review ? '#b8730c' : 'var(--color-hex-500)' }}>
          Game {game.id} · {game.needs_review ? 'check this one' : 'in progress'}
        </span>
        {!game.needs_review && <AutoStatus game={game} />}
        {!canManage && (
          <span className="owner-only-note ml-auto">
            {game.needs_review ? 'The owner is checking the result.' : 'The owner records the result.'}
          </span>
        )}
        {canManage && <div className="ml-auto flex flex-wrap items-center gap-2">
          <div
            className="hidden gap-2 sm:flex"
            title={allMarked ? undefined : 'Entering it yourself? Tap what everyone played. On a win, anyone you skip counts as their first pick. For a loss, mark everyone.'}
          >
            {resultButtons}
          </div>
          <button
            className="btn-secondary"
            disabled={result.isPending}
            onClick={() => confirm('Throw out this spin and re-roll?') && submit('void', 're-roll')}
          >
            Re-roll
          </button>
        </div>}
      </div>
      {game.needs_review && canManage && <ReviewPanel game={game} onResolved={onResolved} />}
      <ErrorText error={result.error} />
      {/* Phones: keep the result buttons in reach without scrolling past every player's card */}
      {canManage && (
        <>
          <div className="h-16 sm:hidden" aria-hidden />
          <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-800 bg-[#06080c]/97 px-4 py-3 sm:hidden">
            <div className="mx-auto flex max-w-7xl items-center gap-2">
              <span className="mr-auto text-xs text-slate-400">Game #{game.id}</span>
              {resultButtons}
            </div>
          </div>
        </>
      )}
    </section>
  )
}

/** Explains whether the Riot auto-matcher is watching this game, with a "Check now" button. */
function AutoStatus({ game }: { game: Game }) {
  const riot = useRiotStatus()
  const { settings } = useActiveRun()
  const playerMap = usePlayerMap()
  const sync = useAction(api.sync)
  const { isAdmin } = useAccess()
  const unlinked = game.assignments
    .map((a) => playerMap.get(a.player_id))
    .filter((p) => p && !p.puuid)
    .map((p) => p!.display_name)

  let text: string
  let watching = false
  if (!riot.data?.key_set) text = 'No Riot key: enter the result yourself.'
  else if (!settings.data?.challenge_mode) text = "Challenge mode is off: this game won't be picked up from Riot."
  else if (unlinked.length) text = `Riot can't record it: ${unlinked.join(', ')} ${unlinked.length > 1 ? 'have' : 'has'} no linked Riot ID.`
  else {
    watching = true
    const secs = settings.data?.poll_interval_seconds ?? 90
    text = `Waiting for the game to end · checking Riot every ${secs}s`
  }
  const outcome = sync.data?.games.find((g) => g.game_id === game.id)
  const live = useLive().data
  const found = live?.game_id === game.id ? live.live : null
  if (found && found.ended_at == null) {
    const t = found.state?.game_time
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
        <span className="h-2 w-2 rounded-full bg-red-500" />
        <span className="text-slate-300">
          In game{t != null ? ` · ${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}` : ''} · picks filled in from the live game
        </span>
        <Link to="/live" className="text-xs text-hex-200 underline">
          Watch live
        </Link>
      </div>
    )
  }

  return (
    <div className="flex min-w-0 flex-col gap-1 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {watching && <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />}
        <span className="text-slate-300">{text}</span>
        {watching && isAdmin && (
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
  const { canManage } = useAccess()
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
        {canManage && (
          <button className="btn-secondary" disabled={undo.isPending} onClick={() => undo.mutate(undefined)}>
            Undo
          </button>
        )}
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
      {game.shields_saved.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-emerald-200">
          <ShieldIcon className="h-4 w-4" />
          Shield saved {game.shields_saved.map((c) => champs.get(c)?.name ?? c).join(', ')}
        </div>
      )}
      {Object.keys(game.gold).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(game.gold).map(([pid, amount]) => (
            <span key={pid} className="flex items-center gap-2 rounded-full bg-white/5 px-3 py-1 text-sm">
              {playerMap.get(Number(pid))?.display_name}
              <GoldBadge amount={amount} />
              {game.grades[pid] && <span className="rounded-full bg-hex-800/70 px-1.5 text-xs text-hex-100">{game.grades[pid]}</span>}
            </span>
          ))}
        </div>
      )}
      {game.contracts.map((c) => (
        <p key={c.player_id} className={`text-sm ${c.status === 'won' ? 'text-gold-200' : 'text-slate-400'}`}>
          {playerMap.get(c.player_id)?.display_name}'s contract ({c.description}):{' '}
          {c.status === 'won' ? `done, +${c.payout} gold` : 'missed'}
        </p>
      ))}
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

/** For players who don't run the wheels: wait for the owner's spin, and set up your own items for it. */
function WaitingForSpin({
  run,
  challengeMode,
  myPlayerId,
  players,
}: {
  run: Run
  challengeMode: boolean
  myPlayerId: number | null
  players: number
}) {
  return (
    <section className="card flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="broadcast-tag" style={{ ['--tag' as string]: 'var(--color-hex-500)' } as CSSProperties}>
          Pre-game
        </span>
        <h2 className="font-semibold">Waiting for the owner to spin</h2>
        <span className="text-xs text-slate-400">Your options show up here once they do.</span>
      </div>
      {challengeMode && run.status === 'active' && myPlayerId != null && (
        <>
          <p className="text-sm text-slate-400">Getting ready? Arm a Blacklist or take a Contract before the spin.</p>
          <PrepRow run={run} playerIds={[myPlayerId]} />
        </>
      )}
      {challengeMode && run.status === 'active' && (
        <>
          <DangerMeter
            alive={run.alive_count}
            total={run.total_count}
            players={players}
            options={run.options_per_player}
            tokens={run.tokens_available}
          />
          <SurvivalOdds run={run} players={players} />
        </>
      )}
    </section>
  )
}

function EndRunButton({ run }: { run: Run }) {
  const end = useAction(() => api.endRun(run.id))
  const navigate = useNavigate()
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-slate-400">Not enough champs left, and no tokens to bring any back.</span>
      <button className="btn-danger" onClick={() => confirm(`End "${run.name}" with ${run.win_count} wins?`) && end.mutate(undefined, { onSuccess: () => navigate(`/runs/${run.id}/recap`) })}>
        End run
      </button>
    </div>
  )
}
