import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { api } from '../api/client'
import { useAction, usePlayerMap, useTokens } from '../hooks/queries'
import { splashUrl } from '../lib/champions'
import { classColor } from '../lib/reel'
import { num, pct } from '../lib/stats'
import type { PoolEntry, Run } from '../types'
import { ErrorText, Modal, Spinner } from './ui'

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col rounded-2xl bg-white/[0.04] px-3 py-2 ring-1 ring-white/5 ring-inset">
      <span className="text-lg font-bold text-slate-100 tabular-nums">{value}</span>
      <span className="text-[10px] tracking-[0.12em] text-slate-400 uppercase">{label}</span>
    </div>
  )
}

/**
 * A champion's card from the Pool tab (SPEC 17.4): art, classes, numbers for this run and the
 * group, plus revive / manual-fix actions. `reviveOnly` opens it straight at the revive choice
 * (used when a champion is dragged out of the Graveyard).
 */
export function ChampionCard({
  run,
  entry,
  onClose,
  onRevived,
  reviveOnly = false,
}: {
  run: Run
  entry: PoolEntry
  onClose: () => void
  /** Called right after a successful revive (before the card closes), e.g. to play the flight. */
  onRevived?: (entry: PoolEntry) => void
  reviveOnly?: boolean
}) {
  const players = usePlayerMap()
  const tokens = useTokens(run.id)
  const report = useQuery({
    queryKey: ['champion-stats', entry.champion_id, run.id],
    queryFn: () => api.championStats(entry.champion_id, run.id),
  })
  const done = { onSuccess: onClose }
  const revived = {
    onSuccess: () => {
      onRevived?.(entry)
      onClose()
    },
  }
  const eliminate = useAction(() => api.eliminate(run.id, entry.champion_id))
  const revive = useAction((tokenId?: number) => api.revive(run.id, entry.champion_id, tokenId))
  const dead = entry.status === 'eliminated'
  const active = run.status === 'active'
  const name = (pid: number | null) => (pid ? (players.get(pid)?.display_name ?? `Player ${pid}`) : null)
  const splash = splashUrl(entry)
  const color = classColor(entry.tags)
  const r = report.data

  const tokenByPlayer = new Map<number, number>()
  for (const t of tokens.data ?? []) if (!tokenByPlayer.has(t.player_id)) tokenByPlayer.set(t.player_id, t.id)

  const reviveButtons =
    tokenByPlayer.size > 0 ? (
      <div className="flex flex-col gap-2">
        <p className="text-sm font-semibold text-gold-100">Use a revive token on {entry.name}:</p>
        <div className="flex flex-wrap gap-2">
          {[...tokenByPlayer].map(([pid, tid]) => (
            <button key={tid} className="btn-primary" disabled={revive.isPending} onClick={() => revive.mutate(tid, revived)}>
              Use {name(pid)}'s token
            </button>
          ))}
        </div>
      </div>
    ) : (
      <p className="text-sm text-slate-400">No revive tokens. Win 3 in a row to get one.</p>
    )

  return (
    <Modal title={reviveOnly ? `Revive ${entry.name}?` : entry.name} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <div className="relative -mx-5 -mt-1 h-40 overflow-hidden sm:h-48">
          {splash && (
            <img
              src={splash}
              alt=""
              className={`h-full w-full object-cover object-[50%_20%] ${dead ? 'grayscale' : ''}`}
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-slate-900 via-slate-900/30 to-transparent" />
          <div className="absolute bottom-3 left-5 flex flex-col">
            <span className="text-sm text-slate-300 capitalize">{entry.title}</span>
            <div className="mt-1 flex gap-1.5">
              {entry.tags.map((t) => (
                <span
                  key={t}
                  className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                  style={{ background: `${t === entry.tags[0] ? color : '#3c3c41'}33`, color: t === entry.tags[0] ? color : '#c3bba8' }}
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
          <span
            className={`absolute top-3 right-5 rounded-full px-2.5 py-1 text-xs font-bold ${
              dead ? 'bg-red-950/80 text-red-200' : 'bg-hex-800/80 text-hex-100'
            }`}
          >
            {dead ? 'In the Graveyard' : 'In the Pool'}
          </span>
        </div>

        {active && dead && reviveButtons}

        {!reviveOnly && (
          <>
            {dead && (
              <p className="text-sm text-red-200">
                Eliminated
                {entry.eliminated_by_player_id && <> when {name(entry.eliminated_by_player_id)} lost with it</>}
                {entry.eliminated_in_game_id && <> in game #{entry.eliminated_in_game_id}</>}
                {entry.eliminated_at && <> on {new Date(entry.eliminated_at).toLocaleDateString()}</>}.
              </p>
            )}
            {report.isLoading && (
              <div className="flex justify-center py-4">
                <Spinner />
              </div>
            )}
            {r && (
              <>
                <div className="grid grid-cols-3 gap-2">
                  <Fact label="Offered" value={r.times_offered} />
                  <Fact label="Played" value={r.times_played} />
                  <Fact label="Record" value={r.times_played ? `${r.wins}-${r.losses}` : '—'} />
                </div>
                {r.played_by.length > 0 && (
                  <p className="text-sm text-slate-300">
                    Played this run by{' '}
                    {r.played_by.map((l, i) => (
                      <span key={l.player_id}>
                        {i > 0 && ', '}
                        <b className="text-gold-100">{name(l.player_id)}</b> ({l.wins}/{l.games})
                      </span>
                    ))}
                  </p>
                )}
                <div className="rounded-2xl bg-white/[0.03] p-3 ring-1 ring-white/5 ring-inset">
                  <div className="mb-2 text-[10px] tracking-[0.12em] text-slate-400 uppercase">Your group on {entry.name}</div>
                  {r.riot_games === 0 && r.all_runs_played === 0 ? (
                    <p className="text-sm text-slate-400">Nobody has played {entry.name} yet.</p>
                  ) : (
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <Fact label="Challenge" value={r.all_runs_played ? `${r.all_runs_wins}-${r.all_runs_played - r.all_runs_wins}` : '—'} />
                      <Fact label="Riot games" value={r.riot_games || '—'} />
                      <Fact
                        label="Win · KDA"
                        value={r.riot_games ? `${pct(r.riot_wins / r.riot_games)} · ${num(r.riot_kda, 1)}` : '—'}
                      />
                    </div>
                  )}
                  {r.riot_players.length > 0 && (
                    <p className="mt-2 text-xs text-slate-400">
                      Most played by {r.riot_players.slice(0, 3).map((l) => `${name(l.player_id)} (${l.games})`).join(', ')}
                    </p>
                  )}
                </div>
              </>
            )}
            <ErrorText error={report.error} />

            {active && (
              <details className="text-sm">
                <summary className="cursor-pointer text-slate-400">Fix a mistake</summary>
                <div className="mt-2 flex gap-2">
                  {dead ? (
                    <button className="btn-secondary" disabled={revive.isPending} onClick={() => revive.mutate(undefined, revived)}>
                      Manual revive (no token)
                    </button>
                  ) : (
                    <button className="btn-danger" disabled={eliminate.isPending} onClick={() => eliminate.mutate(undefined, done)}>
                      Manual eliminate
                    </button>
                  )}
                </div>
                <p className="mt-1 text-xs text-slate-500">Manual changes are logged.</p>
              </details>
            )}
          </>
        )}
        <ErrorText error={eliminate.error ?? revive.error} />
      </div>
    </Modal>
  )
}
