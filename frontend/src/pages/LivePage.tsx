import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { BuildStrip, RoleChip } from '../components/BuildStrip'
import { GoldLeadChart } from '../components/GoldLeadChart'
import { ShieldIcon } from '../components/icons'
import { api } from '../api/client'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState } from '../components/ui'
import {
  useAction,
  useActiveRun,
  useChampionMap,
  useChampions,
  useComp,
  useEconomy,
  useGame,
  useLive,
  usePlayerMap,
  usePlayers,
  usePool,
} from '../hooks/queries'
import { useAccess } from '../hooks/useAuth'
import {
  BLUE,
  DRAGON_COLOR,
  LANE_SHORT,
  RED,
  SIDE_COLOR,
  SIDE_NAME,
  clock,
  contractProgress,
  goldShort,
  pairLanes,
} from '../lib/live'
import { makeDemoLive } from '../lib/liveDemo'
import { queueName } from '../lib/queues'
import { realRoles, rolesByChampion } from '../lib/roles'
import { teamColor } from '../lib/teams'
import type { LiveEvent, LiveGame, LiveIcon, LiveItem, LivePlayer, LiveState, LiveTeam, Role, TeamId } from '../types'

/** Live game tracker: a broadcast-style view of the game a pending spin is being played in. */
export function LivePage() {
  const live = useLive()
  const [params, setParams] = useSearchParams()
  if (params.get('preview') === '1') return <LivePreview onExit={() => setParams({})} />
  if (live.isPending) return <LoadingState />
  const data = live.data
  if (!data?.live) return <NotLive pending={data?.game_id != null} />
  return <Live live={data.live} />
}

function NotLive({ pending }: { pending: boolean }) {
  return (
    <EmptyState title={pending ? 'Waiting for the game to start' : 'No game being tracked'}>
      <p className="max-w-lg text-sm text-slate-400">
        {pending
          ? "Once your game loads, it shows up here by itself and everyone's champion is filled in. This page checks every few seconds."
          : 'Spin on the Wheels tab, then queue up. When the game loads, this page turns into a live tracker.'}
      </p>
      <ul className="max-w-lg text-left text-xs leading-relaxed text-slate-500">
        <li>
          • Finding the game uses your Riot key (Spectator API) and works for any game your linked players are in.
        </li>
        <li>
          • Items, KDA, CS, gold and objectives come from the game client, so they need the app's backend running on a
          PC that's in the game.
        </li>
      </ul>
      <div className="flex flex-wrap justify-center gap-2">
        {!pending && (
          <Link to="/wheels" className="btn-primary">
            Go to Wheels
          </Link>
        )}
        <Link to="/live?preview=1" className="btn-secondary">
          Preview with sample data
        </Link>
      </div>
    </EmptyState>
  )
}

function Live({ live, preview }: { live: LiveGame; preview?: ReactNode }) {
  const st = live.state
  const ended = live.ended_at != null
  return (
    <div className="flex flex-col gap-4">
      {preview}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span
          className="broadcast-tag"
          style={
            {
              ['--tag' as string]: ended ? '#454e5e' : '#e5283c',
            } as CSSProperties
          }
        >
          {!ended && <span className="live-dot" />}
          {ended ? (st?.result ? `Game over · ${st.result === 'Win' ? 'Victory' : 'Defeat'}` : 'Game over') : 'Live'}
        </span>
        <h1 className="text-lg text-white">
          {preview ? 'Sample game' : `Game ${live.game_id}`}
          {live.queue_id != null && <span className="text-slate-400"> · {queueName(live.queue_id)}</span>}
        </h1>
        <span className="ml-auto text-xs text-slate-500">
          {preview
            ? 'Made-up numbers · nothing is saved'
            : live.streaming
            ? 'Live stats from the game client · updates every few seconds'
            : st
              ? 'Live stats paused (the game client on this PC stopped answering)'
              : 'Found through Riot. Live stats need the backend running on a PC in this game.'}
        </span>
      </div>
      {st?.notes?.map((n) => (
        <p key={n} className="text-xs text-amber-300">
          {n}
        </p>
      ))}
      {st ? <Scoreboard live={live} st={st} preview={!!preview} /> : <SpectatorOnly live={live} />}
    </div>
  )
}

// --- score bug ----------------------------------------------------------------------------

function TeamSide({
  team,
  data,
  ours,
  align,
}: {
  team: TeamId
  data: LiveTeam
  ours: boolean
  align: 'left' | 'right'
}) {
  const right = align === 'right'
  return (
    <div className={`flex min-w-0 flex-1 items-center gap-3 ${right ? 'flex-row-reverse text-right' : ''}`}>
      <span className="font-display text-4xl leading-none text-white tabular-nums sm:text-5xl">{data.kills}</span>
      <div className={`flex min-w-0 flex-col gap-1 ${right ? 'items-end' : ''}`}>
        <span
          className="flex items-center gap-2 text-xs font-bold tracking-[0.16em] uppercase"
          style={{ color: '#dfe6f2' }}
        >
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: SIDE_COLOR[team] }} />
          {SIDE_NAME[team]} side
          {ours && <span className="text-gold-300">· you</span>}
        </span>
        <Objectives data={data} right={right} />
      </div>
    </div>
  )
}

function Objectives({ data, right }: { data: LiveTeam; right: boolean }) {
  const chip = (label: string, value: ReactNode, title: string) => (
    <span className="flex items-center gap-1 text-[11px] text-slate-300" title={title}>
      <b className="text-white tabular-nums">{value}</b>
      <span className="text-slate-500">{label}</span>
    </span>
  )
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 ${right ? 'justify-end' : ''}`}>
      {chip(
        'gold',
        goldShort(data.gold),
        'Value of the items the team holds (an estimate: the game only shares gold for this PC’s player)',
      )}
      {chip(data.towers === 1 ? 'tower' : 'towers', data.towers, 'Towers destroyed')}
      {data.inhibitors > 0 && chip('inhibs', data.inhibitors, 'Inhibitors destroyed')}
      {data.grubs > 0 && chip('grubs', data.grubs, 'Void grubs')}
      {data.heralds > 0 && chip('herald', data.heralds, 'Rift Herald')}
      {data.barons > 0 && chip('baron', data.barons, 'Baron Nashor')}
      {data.atakhan > 0 && chip('atakhan', data.atakhan, 'Atakhan')}
      {data.dragons.length > 0 && (
        <span className="flex items-center gap-0.5" title={`Dragons: ${data.dragons.join(', ')}`}>
          {data.dragons.map((d, i) => (
            <span
              key={i}
              className="h-2.5 w-2.5 rotate-45 rounded-[1px]"
              style={{ background: DRAGON_COLOR[d] ?? '#8a93a5' }}
            />
          ))}
        </span>
      )}
    </div>
  )
}

function Scoreboard({ live, st, preview }: { live: LiveGame; st: LiveState; preview: boolean }) {
  const blue = st.teams['100']
  const red = st.teams['200']
  const lead = blue.gold - red.gold
  const leader: TeamId | null = lead > 0 ? BLUE : lead < 0 ? RED : null
  return (
    <>
      <section className="live-bug card grid grid-cols-2 items-center gap-x-4 gap-y-3 px-4 py-4 sm:flex sm:px-5">
        <TeamSide team={BLUE} data={blue} ours={st.our_team === BLUE} align="left" />
        <div className="order-first col-span-2 flex shrink-0 flex-col items-center gap-1 px-2 sm:order-none">
          <span className="font-display text-3xl text-white tabular-nums">{clock(st.game_time)}</span>
          <span className="flex items-center gap-1.5 text-xs text-slate-300 tabular-nums" title="Item gold lead">
            {leader && <span className="h-2 w-2 rounded-sm" style={{ background: SIDE_COLOR[leader] }} />}
            {leader ? `${SIDE_NAME[leader]} +${goldShort(Math.abs(lead))}` : 'Even'}
          </span>
        </div>
        <TeamSide team={RED} data={red} ours={st.our_team === RED} align="right" />
      </section>
      <Bans live={live} />
      <div className="grid gap-4 xl:grid-cols-[1fr_22rem]">
        <div className="flex min-w-0 flex-col gap-4">
          <Lanes st={st} gameId={live.game_id} />
          <Builds
            live={live}
            preview={preview}
            players={st.players
              .filter((p) => p.player_id != null && p.champion_id)
              .map((p) => ({ playerId: p.player_id!, championId: p.champion_id!, items: p.items.map((i) => i.id) }))}
          />
        </div>
        <div className="flex flex-col gap-4">
          <section className="card flex flex-col gap-2 p-4">
            <h2 className="text-sm font-semibold text-white">Gold lead</h2>
            <GoldLeadChart points={st.gold_history} ourTeam={st.our_team} />
          </section>
          <OurTeam st={st} gameId={live.game_id} />
          <Feed events={st.events} />
        </div>
      </div>
    </>
  )
}

function Bans({ live }: { live: LiveGame }) {
  if (!live.bans.length) return null
  const side = (team: TeamId) => live.bans.filter((b) => b.team === team)
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      {[BLUE, RED].map((team) => (
        <div key={team} className={`flex items-center gap-1.5 ${team === RED ? 'flex-row-reverse' : ''}`}>
          <span className="text-[10px] font-bold tracking-[0.14em] text-slate-500 uppercase">
            {SIDE_NAME[team]} bans
          </span>
          {side(team).map((b) => (
            <span key={b.champion_id} className="ban-chip">
              <BanPortrait id={b.champion_id} />
            </span>
          ))}
        </div>
      ))}
    </div>
  )
}

function BanPortrait({ id }: { id: string }) {
  const champs = useChampionMap()
  return <ChampionPortrait champion={champs.get(id)} size="xs" className="rounded-sm grayscale" />
}

// --- lanes --------------------------------------------------------------------------------

function Lanes({ st, gameId }: { st: LiveState; gameId: number }) {
  const rows = pairLanes(st.players)
  return (
    <section className="card flex flex-col gap-1 p-2 sm:p-3" aria-label="Players by lane">
      {rows.map((r, i) => {
        const gold = (r.blue?.item_gold ?? 0) - (r.red?.item_gold ?? 0)
        const cs = (r.blue?.cs ?? 0) - (r.red?.cs ?? 0)
        const lead: TeamId | null = gold > 0 ? BLUE : gold < 0 ? RED : null
        return (
          <div key={i} className="lane-row grid items-center gap-2 md:grid-cols-[1fr_5.5rem_1fr]">
            <PlayerCell p={r.blue} side={BLUE} gameId={gameId} />
            <div className="flex flex-col items-center gap-0.5 py-1 text-center">
              <span className="text-[10px] font-bold tracking-[0.14em] text-slate-500">
                {LANE_SHORT[r.lane] ?? '—'}
              </span>
              <span className="flex items-center gap-1 text-xs text-white tabular-nums" title="Item gold difference">
                {lead && <span className="h-2 w-2 rounded-sm" style={{ background: SIDE_COLOR[lead] }} />}
                {lead ? goldShort(Math.abs(gold)) : 'even'}
              </span>
              <span className="text-[10px] text-slate-400 tabular-nums" title="CS difference (blue minus red)">
                CS {cs > 0 ? '+' : cs < 0 ? '−' : ''}
                {Math.abs(cs)}
              </span>
            </div>
            <PlayerCell p={r.red} side={RED} gameId={gameId} />
          </div>
        )
      })}
    </section>
  )
}

function Icon({
  icon,
  size = 18,
  round = false,
}: {
  icon: LiveIcon | null | undefined
  size?: number
  round?: boolean
}) {
  if (!icon) return <span style={{ width: size, height: size }} className="inline-block rounded-sm bg-white/5" />
  return icon.icon ? (
    <img
      src={icon.icon}
      alt={icon.name ?? ''}
      title={icon.name ?? ''}
      width={size}
      height={size}
      className={round ? 'rounded-full' : 'rounded-sm'}
    />
  ) : (
    <span
      title={icon.name ?? ''}
      style={{ width: size, height: size }}
      className="inline-grid place-items-center rounded-sm bg-white/10 text-[8px] text-slate-300"
    >
      {(icon.name ?? '?').slice(0, 2)}
    </span>
  )
}

function Items({ items, right }: { items: LiveItem[]; right: boolean }) {
  const slots = Array.from({ length: 7 }, (_, i) => items.find((it) => it.slot === i))
  return (
    <div className={`flex gap-0.5 ${right ? 'flex-row-reverse' : ''}`}>
      {slots.map((it, i) =>
        it?.image ? (
          <img
            key={i}
            src={it.image}
            alt={it.name ?? ''}
            title={it.name ?? ''}
            className={`h-6 w-6 rounded-sm ${i === 6 ? 'ml-1 rounded-full' : ''}`}
          />
        ) : (
          <span
            key={i}
            title={it?.name ?? undefined}
            className={`h-6 w-6 rounded-sm bg-white/[0.04] ring-1 ring-white/5 ring-inset ${i === 6 ? 'ml-1 rounded-full' : ''}`}
          />
        ),
      )}
    </div>
  )
}

function PlayerCell({ p, side, gameId }: { p: LivePlayer | undefined; side: TeamId; gameId: number }) {
  const champs = useChampionMap()
  const players = usePlayerMap()
  const pool = usePool(useActiveRun().runId)
  if (!p) return <div />
  const right = side === RED
  const c = p.champion_id ? champs.get(p.champion_id) : undefined
  const ours = p.player_id != null ? players.get(p.player_id) : undefined
  const shielded = !!p.champion_id && (pool.data ?? []).some((e) => e.champion_id === p.champion_id && e.shield_item_id)
  const optionTag = p.player_id == null ? null : p.option_index == null ? 'Other' : `#${p.option_index + 1}`
  return (
    <div
      className={`live-player flex min-w-0 items-center gap-2.5 rounded-sm px-2 py-1.5 ${right ? 'flex-row-reverse text-right' : ''} ${ours ? 'is-ours' : ''}`}
      style={
        {
          ['--team' as string]: ours ? teamColor(ours.id) : SIDE_COLOR[side],
        } as CSSProperties
      }
      data-game={gameId}
    >
      <div className="relative shrink-0">
        <ChampionPortrait champion={c} size="sm" eager className={`rounded-sm ${p.dead ? 'grayscale' : ''}`} />
        <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 rounded-sm bg-black/85 px-1 text-[10px] font-bold text-white tabular-nums">
          {p.level}
        </span>
        {p.dead && (
          <span
            className="absolute inset-0 grid place-items-center rounded-sm bg-black/55 text-sm font-bold text-red-200 tabular-nums"
            title="Respawning"
          >
            {p.respawn}
          </span>
        )}
      </div>
      <div className={`flex min-w-0 flex-1 flex-col gap-1 ${right ? 'items-end' : ''}`}>
        <div className={`flex max-w-full min-w-0 items-center gap-1.5 ${right ? 'flex-row-reverse' : ''}`}>
          <span className={`truncate text-sm font-semibold ${ours ? 'text-white' : 'text-slate-200'}`}>
            {ours?.display_name ?? c?.name ?? 'Opponent'}
          </span>
          {optionTag && (
            <span
              className="shrink-0 rounded-sm bg-gold-500/20 px-1 text-[10px] font-bold text-gold-200"
              title="Which of their spin options this is"
            >
              {optionTag}
            </span>
          )}
          {shielded && (
            <span title="Shielded: a loss won't eliminate it" className="text-emerald-300">
              <ShieldIcon className="h-3.5 w-3.5" />
            </span>
          )}
          {ours && <span className="hidden truncate text-xs text-slate-500 lg:inline">{c?.name}</span>}
        </div>
        <div className={`flex items-center gap-2 ${right ? 'flex-row-reverse' : ''}`}>
          <span className={`flex gap-0.5 ${right ? 'flex-row-reverse' : ''}`}>
            <Icon icon={p.spells[0]} />
            <Icon icon={p.spells[1]} />
            <Icon icon={p.keystone} round />
          </span>
          <span className="text-sm text-white tabular-nums">
            {p.kills}/{p.deaths}/{p.assists}
          </span>
          <span className="text-xs text-slate-400 tabular-nums">{p.cs} cs</span>
        </div>
        <Items items={p.items} right={right} />
      </div>
    </div>
  )
}

// --- side column --------------------------------------------------------------------------

function OurTeam({ st, gameId }: { st: LiveState; gameId: number }) {
  const { run } = useActiveRun()
  const economy = useEconomy(run.data?.id)
  const players = usePlayerMap()
  const ours = st.players.filter((p) => p.player_id != null)
  const contracts = (economy.data ?? [])
    .filter((e) => e.active_contract && ours.some((p) => p.player_id === e.player_id))
    .map((e) => ({ e, p: ours.find((p) => p.player_id === e.player_id) }))
  if (!contracts.length) return null
  return (
    <section className="card flex flex-col gap-2.5 p-4" data-game={gameId}>
      <h2 className="text-sm font-semibold text-white">Contracts</h2>
      {contracts.map(({ e, p }) => {
        const c = e.active_contract!
        const prog = contractProgress(c.goal_type, c.target, p)
        const pct = prog ? Math.min(100, (prog.now / Math.max(1, prog.target)) * 100) : 0
        return (
          <div key={e.player_id} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="text-slate-200">
                <b style={{ color: teamColor(e.player_id) }}>{players.get(e.player_id)?.display_name}</b> ·{' '}
                {c.description}
              </span>
              <span className="text-slate-400 tabular-nums">
                {prog ? (prog.now >= prog.target ? `Done · ${prog.now}/${prog.target}` : `${prog.now}/${prog.target}`) : 'after the game'}
              </span>
            </div>
            {prog && (
              <div className="h-1.5 overflow-hidden rounded-full bg-gold-900/60">
                <div
                  className="h-full rounded-full bg-gold-400 transition-[width] duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
            )}
          </div>
        )
      })}
    </section>
  )
}

type Who = LiveEvent['killer']

function eventText(e: LiveEvent, name: (w: Who) => string): string {
  switch (e.type) {
    case 'kill':
      return `${name(e.killer)} killed ${name(e.victim)}`
    case 'first_blood':
      return `First blood: ${name(e.killer)}`
    case 'multikill':
      return `${name(e.killer)}: ${['', '', 'double', 'triple', 'quadra', 'penta'][e.streak ?? 0] ?? 'multi'} kill`
    case 'ace':
      return 'Ace'
    case 'dragon':
      return `${e.detail ?? ''} dragon${e.stolen ? ' (stolen)' : ''}`
    case 'baron':
      return `Baron${e.stolen ? ' (stolen)' : ''}`
    case 'herald':
      return 'Rift Herald'
    case 'grubs':
      return 'Void grubs'
    case 'atakhan':
      return 'Atakhan'
    case 'tower':
      return 'Tower destroyed'
    case 'inhibitor':
      return 'Inhibitor destroyed'
  }
}

function Feed({ events }: { events: LiveEvent[] }) {
  const players = usePlayerMap()
  // Riot names of our players read better as their app names.
  const champs = useChampionMap()
  // Our players by their app name, everyone else by champion (in-game names are never stored).
  const name = (w: Who) =>
    !w
      ? 'Someone'
      : w.player_id != null
        ? (players.get(w.player_id)?.display_name ?? 'Someone')
        : (champs.get(w.champion_id ?? '')?.name ?? 'Someone')
  const big = new Set(['first_blood', 'multikill', 'ace', 'baron', 'dragon', 'atakhan'])
  return (
    <section className="card flex max-h-80 flex-col gap-2 overflow-y-auto p-4">
      <h2 className="text-sm font-semibold text-white">Play-by-play</h2>
      {events.length === 0 && <p className="text-xs text-slate-500">Nothing yet.</p>}
      <ol className="flex flex-col gap-1">
        {events.map((e, i) => (
          <li key={i} className="flex items-center gap-2 text-xs">
            <span className="w-10 shrink-0 text-slate-500 tabular-nums">{clock(e.t)}</span>
            <span
              className="h-2 w-2 shrink-0 rounded-sm"
              style={{ background: e.team ? SIDE_COLOR[e.team] : '#5b6475' }}
            />
            <span className={big.has(e.type) ? 'font-semibold text-white' : 'text-slate-300'}>
              {eventText(e, name)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}

// --- found through Spectator, no live stats -------------------------------------------------

function SpectatorOnly({ live }: { live: LiveGame }) {
  const champs = useChampionMap()
  const players = usePlayerMap()
  return (
    <>
      <Bans live={live} />
      <Builds
        live={live}
        players={live.participants
          .filter((p) => p.player_id != null && p.champion_id)
          .map((p) => ({ playerId: p.player_id!, championId: p.champion_id! }))}
      />
      <div className="grid gap-4 md:grid-cols-2">
        {[BLUE, RED].map((team) => (
          <section
            key={team}
            className="card flex flex-col gap-2 p-4"
            style={{ borderTop: `3px solid ${SIDE_COLOR[team]}` }}
          >
            <h2 className="text-sm font-semibold text-white">
              {SIDE_NAME[team]} side
              {live.our_team === team && <span className="text-gold-300"> · you</span>}
            </h2>
            {live.participants
              .filter((p) => p.team === team)
              .map((p, i) => {
                const ours = p.player_id != null ? players.get(p.player_id) : undefined
                return (
                  <div key={i} className="flex items-center gap-2.5">
                    <ChampionPortrait
                      champion={p.champion_id ? champs.get(p.champion_id) : undefined}
                      size="sm"
                      className="rounded-sm"
                    />
                    <span className="flex-1 truncate text-sm">
                      {ours ? (
                        <b style={{ color: teamColor(ours.id) }}>{ours.display_name}</b>
                      ) : (
                        <span className="text-slate-400">Opponent</span>
                      )}{' '}
                      <span className="text-slate-500">{p.champion_id ? champs.get(p.champion_id)?.name : ''}</span>
                    </span>
                    <span className="flex gap-0.5">
                      {p.spells.map((s, j) => (
                        <Icon key={j} icon={s} size={20} />
                      ))}
                      <Icon icon={p.keystone} size={20} round />
                    </span>
                  </div>
                )
              })}
          </section>
        ))}
      </div>
    </>
  )
}

// --- builds for our players (so nobody has to flip back to the Wheels tab mid-game) ---------------

function Builds({
  live,
  players,
  preview = false,
}: {
  live: LiveGame
  players: { playerId: number; championId: string; items?: number[] }[]
  preview?: boolean
}) {
  const champs = useChampionMap()
  const names = usePlayerMap()
  const { canActFor } = useAccess()
  // Builds follow the role each player is really in: set by hand, their lane in the game, or Smite.
  const roles = realRoles(undefined, live)
  const comp = useComp(
    players.map((p) => p.championId),
    [],
    rolesByChampion(players, roles),
  )
  const setRole = useAction(({ playerId, role }: { playerId: number; role: Role | null }) =>
    api.setRole(live.game_id, playerId, role),
  )
  const picks = new Map((comp.data?.picks ?? []).map((p) => [p.champion_id, p]))
  if (!players.length) return null
  return (
    <section className="card flex flex-col gap-3 p-4" aria-label="Your builds">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-white">Your builds</h2>
        <span className="text-[11px] text-slate-500">
          High-elo runes, spells and core items for the role they're in · ✓ already built · M opens the full
          Mobalytics build
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
        {players.map((p) => {
          const pick = picks.get(p.championId)
          const owned = p.items ? new Set(p.items) : undefined
          const core = pick?.items ?? []
          const built = owned ? core.filter((i) => owned.has(i.id)).length : null
          return (
            <div
              key={p.playerId}
              className="flex flex-col gap-2 rounded-sm bg-white/[0.03] p-2.5 ring-1 ring-white/5 ring-inset"
              style={{ boxShadow: `inset 2px 0 0 ${teamColor(p.playerId)}` }}
            >
              <div className="flex items-center gap-2">
                <ChampionPortrait champion={champs.get(p.championId)} size="xs" className="rounded-sm" />
                <span className="min-w-0 truncate text-sm font-semibold" style={{ color: teamColor(p.playerId) }}>
                  {names.get(p.playerId)?.display_name}
                </span>
                <span className="truncate text-xs text-slate-400">{champs.get(p.championId)?.name}</span>
                <RoleChip
                  pick={pick}
                  real={roles.get(p.playerId)}
                  onSet={!preview && canActFor(p.playerId) ? (role) => setRole.mutate({ playerId: p.playerId, role }) : undefined}
                  busy={setRole.isPending}
                />
                {built != null && core.length > 0 && (
                  <span className="ml-auto shrink-0 text-[10px] text-slate-400 tabular-nums" title="Core items built so far">
                    core {built}/{core.length}
                  </span>
                )}
              </div>
              <BuildStrip pick={pick} loading={comp.isLoading} owned={owned} />
            </div>
          )
        })}
      </div>
      <ErrorText error={setRole.error} />
    </section>
  )
}

// --- preview with sample data ----------------------------------------------------------------

/**
 * The Live tab filled with a made-up game, to check how it looks without being in one. Uses the
 * current spin's players and champions (or the roster with sample champions), real art and the real
 * build suggestions. Runs only in the browser: nothing is saved, nothing calls Riot.
 */
function LivePreview({ onExit }: { onExit: () => void }) {
  const champions = useChampions()
  const players = usePlayers()
  const { run } = useActiveRun()
  const game = useGame(run.data?.pending_game_id)
  const [t, setT] = useState(14 * 60)
  const [speed, setSpeed] = useState(1)

  useEffect(() => {
    if (!speed) return
    const id = setInterval(() => setT((x) => Math.min(x + speed, 45 * 60)), 1000)
    return () => clearInterval(id)
  }, [speed])

  const ours = useMemo(() => {
    const spin = game.data?.status === 'pending' ? game.data.assignments : []
    if (spin.length) return spin.map((a) => ({ playerId: a.player_id, championId: a.played_champion_id ?? a.options[0] }))
    // No spin going: up to five players on sample champions.
    const list = champions.data ?? []
    return (players.data ?? []).slice(0, 5).map((p, i) => ({ playerId: p.id, championId: list[(i * 37 + 11) % Math.max(1, list.length)]?.id }))
  }, [game.data, players.data, champions.data])

  if (!champions.data?.length) return <LoadingState />
  const live = makeDemoLive({
    ours: ours.filter((o): o is { playerId: number; championId: string } => !!o.championId),
    champions: champions.data,
    t,
    gameId: game.data?.id,
  })

  const banner = (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-sm bg-amber-500/10 px-3 py-2 text-xs text-amber-100 ring-1 ring-amber-400/30 ring-inset">
      <span className="broadcast-tag" style={{ ['--tag' as string]: '#b8730c' } as CSSProperties}>
        Preview
      </span>
      <span>
        A made-up game so you can see the Live tab. {ours.length ? 'Your team is the current spin or your roster.' : ''} Real
        games replace this automatically.
      </span>
      <span className="ml-auto flex items-center gap-1.5">
        <span className="text-amber-200/70">Clock</span>
        {[0, 1, 10].map((s) => (
          <button
            key={s}
            className={`rounded-sm px-2 py-0.5 ring-1 ring-inset ${speed === s ? 'bg-amber-400/25 ring-amber-300/60' : 'ring-amber-300/25 hover:bg-amber-400/10'}`}
            onClick={() => setSpeed(s)}
          >
            {s === 0 ? 'Pause' : `${s}×`}
          </button>
        ))}
        <button className="rounded-sm px-2 py-0.5 ring-1 ring-amber-300/25 ring-inset hover:bg-amber-400/10" onClick={() => setT(14 * 60)}>
          Restart
        </button>
        <button className="btn-secondary ml-1 px-3 py-1 text-xs" onClick={onExit}>
          Exit preview
        </button>
      </span>
    </div>
  )
  return <Live live={live} preview={banner} />
}
