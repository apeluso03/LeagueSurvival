import { pct } from '../lib/stats'
import type { CompPick, MetaItemInfo, Role, RuneRef } from '../types'

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

/** One champion's high-elo build in two compact rows: rune page, then core items and boots. */
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
        </div>
      ) : (
        <span className="text-[11px] text-slate-500">No high-elo build yet</span>
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
