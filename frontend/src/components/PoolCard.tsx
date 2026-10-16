import { memo } from 'react'
import { loadingUrl } from '../lib/champions'
import { classColor } from '../lib/reel'
import type { ChampionLine, Player, PoolEntry } from '../types'
import { BlacklistIcon, ShieldIcon, SkullIcon, WheelIcon } from './icons'

export type CardAction = 'revive' | 'shield'

type Props = {
  entry: PoolEntry
  line: ChampionLine | undefined
  players: Map<number, Player>
  compact: boolean
  /** Hover quick action, when someone can use it on this champion. */
  action: CardAction | null
  onOpen: (e: PoolEntry) => void
  onAction: (e: PoolEntry, action: CardAction) => void
}

const names = (ids: number[], players: Map<number, Player>) =>
  [...new Set(ids)].map((id) => players.get(id)?.display_name ?? `Player ${id}`)

/** "On Alex's list" / "On Alex's and Sam's lists". */
function listsText(who: string[]) {
  if (who.length === 1) return `On ${who[0]}'s list`
  if (who.length === 2) return `On ${who[0]}'s and ${who[1]}'s lists`
  return `On ${who.length} lists`
}

function statLine(e: PoolEntry, l: ChampionLine | undefined, players: Map<number, Player>) {
  if (e.status === 'eliminated') {
    const by = e.eliminated_by_player_id ? names([e.eliminated_by_player_id], players)[0] : null
    const game = e.eliminated_in_game_id ? `game #${e.eliminated_in_game_id}` : null
    return [by ? `Lost by ${by}` : 'Eliminated', game].filter(Boolean).join(' · ')
  }
  if (l?.played) return `Played ${l.played} · ${l.wins}–${l.losses}`
  if (l?.offered) return `Rolled ${l.offered}× · never played`
  return 'Never rolled'
}

/**
 * One champion on the Pool tab: tall art, class strip, short numbers and power-up badges.
 * Memoized, so typing in search only re-renders the cards that change.
 */
export const PoolCard = memo(function PoolCard({ entry: e, line: l, players, compact, action, onOpen, onAction }: Props) {
  const dead = e.status === 'eliminated'
  const color = classColor(e.tags)
  const art = loadingUrl(e)
  const shieldBy = e.shield_player_id ? names([e.shield_player_id], players)[0] : null
  const spinners = names(l?.on_spin ?? [], players)
  const blockers = names(l?.blacklisted_by ?? [], players)
  const rate = l?.played ? l.wins / l.played : null

  return (
    // The small square portrait (usually cached already) shows until the tall art loads.
    <div
      className={`pool-card ${dead ? 'is-dead' : ''}`}
      data-card-id={e.champion_id}
      style={{ backgroundImage: `url(${e.image_url})` }}
    >
      <button
        type="button"
        onClick={() => onOpen(e)}
        className="absolute inset-0 text-left"
        aria-label={`${e.name}${dead ? ', eliminated' : ''}. Show details`}
      >
        {art ? (
          <img src={art} alt="" loading="lazy" decoding="async" draggable={false} className="pool-card-art" />
        ) : (
          <div className="pool-card-art bg-slate-800" />
        )}
        <span className="absolute inset-x-0 top-0 h-[3px]" style={{ background: color }} aria-hidden />
        <span className="pool-card-shade" aria-hidden />

        <span className={`absolute flex flex-col justify-end ${compact ? 'inset-x-2 bottom-2' : 'inset-x-3 bottom-3'}`}>
          <span
            className={`truncate font-display font-bold tracking-wide ${compact ? 'text-sm' : 'text-base'} ${
              dead ? 'text-slate-300' : 'text-gold-100'
            }`}
          >
            {e.name}
          </span>
          {!compact && (
            <span className="text-[10px] font-semibold tracking-[0.14em] uppercase" style={{ color: dead ? undefined : color }}>
              {e.tags.join(' · ')}
            </span>
          )}
          <span className={`truncate text-slate-300 ${compact ? 'text-[10px]' : 'mt-0.5 text-xs'}`}>{statLine(e, l, players)}</span>
          <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-white/10" aria-hidden>
            {rate !== null && (
              <span
                className="block h-full rounded-full"
                style={{ width: `${Math.max(6, rate * 100)}%`, background: rate >= 0.5 ? 'var(--color-hex-300)' : '#e0434f' }}
              />
            )}
          </span>
        </span>
      </button>

      {/* Power-ups and status, top corners */}
      <span className="pointer-events-none absolute top-2 left-2 flex flex-col gap-1">
        {e.shield_item_id && (
          <span className="pool-badge bg-emerald-600 text-white" title={`Shielded${shieldBy ? ` by ${shieldBy}` : ''}`}>
            <ShieldIcon className="h-3.5 w-3.5" strokeWidth={2.4} />
          </span>
        )}
        {blockers.length > 0 && (
          <span className="pool-badge bg-red-700 text-white" title={`Blacklisted by ${blockers.join(', ')} for their next spin`}>
            <BlacklistIcon className="h-3.5 w-3.5" strokeWidth={2.4} />
          </span>
        )}
      </span>
      {dead && (
        <span className="pool-badge absolute top-2 right-2 bg-black/70 text-red-300 ring-1 ring-red-400/40" title="Eliminated">
          <SkullIcon className="h-3.5 w-3.5" strokeWidth={2} />
        </span>
      )}
      {spinners.length > 0 && !dead && (
        <span
          className={`pointer-events-none absolute right-2 flex items-center gap-1 rounded-full bg-gold-500/90 px-2 py-0.5 text-[10px] font-bold text-slate-950 shadow ${
            compact ? 'top-2 max-w-[calc(100%-1rem)]' : 'top-2 max-w-[calc(100%-2.5rem)]'
          }`}
          title={listsText(spinners)}
        >
          <WheelIcon className="h-3 w-3 shrink-0" strokeWidth={2.4} />
          {!compact && <span className="truncate">{listsText(spinners)}</span>}
        </span>
      )}

      {action && (
        <button type="button" className="pool-card-action" data-kind={action} onClick={() => onAction(e, action)}>
          {action === 'revive' ? '✦ Revive' : (
            <>
              <ShieldIcon className="h-3.5 w-3.5" strokeWidth={2.2} /> Shield
            </>
          )}
        </button>
      )}
    </div>
  )
})
