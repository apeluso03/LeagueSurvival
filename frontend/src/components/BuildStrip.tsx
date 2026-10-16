import type { CSSProperties } from 'react'
import { useChampionMap } from '../hooks/queries'
import { pct } from '../lib/stats'
import type { BanSuggestion, CompPick, MetaItemInfo, Role, RuneRef, SpellPair } from '../types'
import { ChampionPortrait } from './ui'

const ROLE_SHORT: Record<Role, string> = { TOP: 'TOP', JUNGLE: 'JG', MIDDLE: 'MID', BOTTOM: 'BOT', UTILITY: 'SUP' }
const ROLE_NAME: Record<Role, string> = { TOP: 'Top', JUNGLE: 'Jungle', MIDDLE: 'Mid', BOTTOM: 'Bot', UTILITY: 'Support' }

/** Suggested role as a small chip; hover for the high-elo numbers behind it. */
export function RoleChip({ pick }: { pick: CompPick | undefined }) {
  if (!pick) return null
  const tip = pick.off_role
    ? `Suggested: ${pick.role_name} (off-role, rarely played there)`
    : pick.role_source === 'high-elo'
      ? `Suggested: ${pick.role_name} · ${pick.role_games.toLocaleString()} high-elo games${
          pick.role_win_rate != null ? `, ${pct(pick.role_win_rate)} win rate` : ''
        }`
      : `Suggested: ${pick.role_name} (from champion data)`
  return (
    <span className={`role-chip ${pick.off_role ? 'is-off' : ''}`} title={tip}>
      {ROLE_SHORT[pick.role]}
    </span>
  )
}

function RuneIcon({ rune, size, title }: { rune: RuneRef | null | undefined; size: number; title?: string }) {
  if (!rune?.icon) return null
  return <img src={rune.icon} alt={rune.name} title={title ?? rune.name} width={size} height={size} className="shrink-0" />
}

function ItemIcon({ item, boots = false }: { item: MetaItemInfo; boots?: boolean }) {
  const tip = `${item.name}${item.pick_rate != null ? ` · built in ${pct(item.pick_rate)} of games` : ''}${
    item.win_rate != null ? ` · ${pct(item.win_rate)} win rate` : ''
  }`
  return item.image ? (
    <img
      src={item.image}
      alt={item.name}
      title={tip}
      className={`h-7 w-7 shrink-0 rounded-sm ring-1 ${boots ? 'ring-slate-500/60' : 'ring-gold-500/60'}`}
    />
  ) : null
}

function Spells({ pair }: { pair: SpellPair }) {
  const tip = `${pair.spells.map((s) => s.name).join(' + ')}${
    pair.pick_rate != null ? ` · taken in ${pct(pair.pick_rate)} of games` : ''
  }${pair.win_rate != null ? ` · ${pct(pair.win_rate)} win rate` : ''}`
  return (
    <span className="ml-auto flex shrink-0 gap-0.5" title={tip}>
      {pair.spells.map((s) =>
        s.icon ? (
          <img key={s.id} src={s.icon} alt={s.name} width={22} height={22} className="rounded-sm ring-1 ring-white/15" />
        ) : (
          <span key={s.id} className="text-[10px] text-slate-400">
            {s.name}
          </span>
        ),
      )}
    </span>
  )
}

/** One champion's high-elo build in two compact rows: rune page and summoner spells, then core items and boots. */
export function BuildStrip({ pick, loading = false }: { pick: CompPick | undefined; loading?: boolean }) {
  if (!pick) return <div className="build-strip text-[11px] text-slate-500">{loading ? 'Loading build...' : ''}</div>
  const r = pick.runes
  const all = r ? [...r.primary_perks, ...r.secondary_perks].map((p) => p.name).join(', ') : ''
  return (
    <div className="build-strip flex flex-col gap-1.5">
      {pick.off_role && (
        <span className="text-[10px] leading-tight text-amber-300">
          Off-role · build from its usual {pick.build_role ? ROLE_NAME[pick.build_role] : 'role'}
        </span>
      )}
      {r ? (
        <div className="flex min-w-0 items-center gap-1.5" title={`${r.keystone?.name} · ${r.primary.name} / ${r.secondary.name}: ${all}`}>
          <RuneIcon rune={r.keystone} size={28} />
          <RuneIcon rune={r.primary} size={15} title={`Primary: ${r.primary.name}`} />
          <RuneIcon rune={r.secondary} size={15} title={`Secondary: ${r.secondary.name}`} />
          <span className="min-w-0 truncate text-[11px] text-slate-300">
            {r.keystone?.name}
            {r.win_rate != null && <span className="text-slate-500"> · {pct(r.win_rate)}</span>}
          </span>
          {pick.spells && <Spells pair={pick.spells} />}
        </div>
      ) : (
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-slate-500">No high-elo build yet</span>
          {pick.spells && <Spells pair={pick.spells} />}
        </div>
      )}
      {(pick.items.length > 0 || pick.boots) && (
        <div className="flex items-center gap-1">
          {pick.items.map((i) => (
            <ItemIcon key={i.id} item={i} />
          ))}
          {pick.boots && (
            <>
              <span className="mx-0.5 text-[10px] text-slate-500">+</span>
              <ItemIcon item={pick.boots} boots />
            </>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Suggested bans: the enemy champions the rolled champions do worst against in high elo.
 * Each portrait shows the rolled champions' combined win rate against it; hover for the details.
 */
export function BanStrip({ bans, loading = false }: { bans: BanSuggestion[] | undefined; loading?: boolean }) {
  const champs = useChampionMap()
  const name = (id: string) => champs.get(id)?.name ?? id
  return (
    <div className="ban-strip flex items-center gap-1.5">
      <span className="broadcast-tag shrink-0" style={{ ['--tag' as string]: '#a3202f' } as CSSProperties}>
        Bans
      </span>
      {loading && !bans ? (
        <span className="text-[11px] text-slate-500">Loading...</span>
      ) : !bans?.length ? (
        <span className="text-[11px] text-slate-500" title="Bans come from high-elo matchups the app has collected. Check Settings, High-elo data.">
          Not enough matchup data yet
        </span>
      ) : (
        bans.map((b) => {
          const c = champs.get(b.champion_id)
          const detail = b.against
            .map((a) => `${name(a.champion_id)} ${a.win_rate != null ? pct(a.win_rate) : '—'} of ${a.games}`)
            .join(', ')
          const tip = `Ban ${name(b.champion_id)}: your champions win ${b.win_rate != null ? pct(b.win_rate) : '—'} of ${b.games} high-elo games against it (${detail})`
          return (
            <span key={b.champion_id} className="ban-chip" title={tip}>
              <ChampionPortrait champion={c} size="xs" className="rounded-sm" />
              {b.win_rate != null && <span className="ban-rate">{pct(b.win_rate)}</span>}
            </span>
          )
        })
      )}
    </div>
  )
}
