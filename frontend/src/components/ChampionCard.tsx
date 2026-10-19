import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { api } from '../api/client'
import { useAction, useChampionLines, useEconomy, usePlayerMap, useTokens } from '../hooks/queries'
import { splashUrl } from '../lib/champions'
import { classColor } from '../lib/reel'
import { num, pct } from '../lib/stats'
import type { PoolEntry, Run } from '../types'
import { useAccess } from '../hooks/useAuth'
import { useOwnedItem } from '../hooks/useItems'
import { BlacklistIcon, ShieldIcon, WheelIcon } from './icons'
import { MobaWidget } from './MobaWidget'
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
 * group, plus revive / shield / manual-fix actions. `focus` opens it at just one action (the
 * Revive and Shield buttons on the Pool cards).
 */
export function ChampionCard({
  run,
  entry,
  onClose,
  onRevived,
  focus,
}: {
  run: Run
  entry: PoolEntry
  onClose: () => void
  /** Called right after a successful revive (before the card closes), e.g. to play the animation. */
  onRevived?: (entry: PoolEntry) => void
  focus?: 'revive' | 'shield'
}) {
  const players = usePlayerMap()
  const tokens = useTokens(run.id)
  const line = useChampionLines(run.id).data?.[entry.champion_id]
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

  const { canManage, canActFor } = useAccess(run)
  // Only tokens you may spend: your own (the run's owner can spend anyone's).
  const tokenByPlayer = new Map<number, number>()
  for (const t of tokens.data ?? []) if (canActFor(t.player_id) && !tokenByPlayer.has(t.player_id)) tokenByPlayer.set(t.player_id, t.id)

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
      <p className="text-sm text-slate-400">
        {canManage ? 'No revive tokens.' : "You don't have a revive token."} Win 3 in a row to get one.
      </p>
    )

  return (
    <Modal title={focus === 'revive' ? `Revive ${entry.name}?` : focus === 'shield' ? `Shield ${entry.name}?` : entry.name} onClose={onClose}>
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
            {dead ? 'Eliminated' : 'Alive'}
          </span>
        </div>

        {active && dead && focus !== 'shield' && reviveButtons}
        {!dead && entry.shield_item_id && focus !== 'revive' && (
          <p className="flex items-center gap-2 text-sm text-emerald-200">
            <ShieldIcon className="h-4 w-4" />
            Shielded{entry.shield_player_id ? ` by ${name(entry.shield_player_id)}` : ''}. The next loss with it breaks the
            shield instead.
          </p>
        )}
        {!focus && !dead && !!line?.on_spin.length && (
          <p className="flex items-center gap-2 text-sm text-gold-200">
            <WheelIcon className="h-4 w-4 shrink-0" />
            On {[...new Set(line.on_spin)].map((p) => `${name(p)}'s`).join(' and ')} list in the current spin.
          </p>
        )}
        {!focus && !dead && !!line?.blacklisted_by.length && (
          <p className="flex items-center gap-2 text-sm text-red-200">
            <BlacklistIcon className="h-4 w-4 shrink-0" />
            Blacklisted by {line.blacklisted_by.map(name).join(' and ')}: it won't show up in their next spin.
          </p>
        )}
        {active && !dead && !entry.shield_item_id && focus !== 'revive' && <ShieldPlacer run={run} entry={entry} onDone={onClose} />}

        {!focus && (
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
            <MobaSection championId={entry.champion_id} />

            {active && canManage && (
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

/** Place an owned Shield on this champion (SPEC 10.3 shield flow). */
function ShieldPlacer({ run, entry, onDone }: { run: Run; entry: PoolEntry; onDone: () => void }) {
  const economy = useEconomy(run.id)
  const players = usePlayerMap()
  const owned = useOwnedItem(run.id)
  const holders = (economy.data ?? []).filter((e) => (e.unused.shield ?? 0) > 0)
  if (!holders.length) return null
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-semibold text-gold-100">Protect {entry.name} with a shield:</p>
      <div className="flex flex-wrap gap-2">
        {holders.map((h) => (
          <button
            key={h.player_id}
            className="btn-secondary"
            disabled={owned.isPending}
            onClick={() =>
              owned.mutate(
                { playerId: h.player_id, type: 'shield', body: { champion_id: entry.champion_id } },
                { onSuccess: onDone },
              )
            }
          >
            <ShieldIcon className="h-4 w-4 text-emerald-300" />
            Use {players.get(h.player_id)?.display_name}'s shield
          </button>
        ))}
      </div>
      <ErrorText error={owned.error} />
    </div>
  )
}

/** Mobalytics' build for this champion, loaded only when opened. */
function MobaSection({ championId }: { championId: string }) {
  const [open, setOpen] = useState(false)
  return (
    <details className="text-sm" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-slate-400">Mobalytics build</summary>
      {open && (
        <div className="mt-2">
          <MobaWidget championId={championId} compact />
        </div>
      )}
    </details>
  )
}
