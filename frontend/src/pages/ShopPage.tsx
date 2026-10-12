import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ContractReveal } from '../components/ContractReveal'
import { GoldBadge } from '../components/Gold'
import { BlacklistDialog, PickChampionDialog } from '../components/ItemDialogs'
import { EmptyState, ErrorText, LoadingState } from '../components/ui'
import {
  useAction,
  useActiveRun,
  useChampionMap,
  useEconomy,
  useGold,
  useInventory,
  usePlayers,
  usePool,
  useShop,
} from '../hooks/queries'
import { ITEM_META, ITEM_ORDER, signedGold } from '../lib/items'
import type { ContractInfo, InventoryItem, ItemType, LedgerRow, Run, ShopItem } from '../types'

export function ShopPage() {
  const { run, runId } = useActiveRun()
  if (!runId) {
    return (
      <EmptyState title="No active run">
        <Link to="/settings" className="btn-primary">
          Start a run
        </Link>
      </EmptyState>
    )
  }
  if (!run.data) return <LoadingState />
  return <Shop run={run.data} />
}

const PLAYER_KEY = 'lol-survival:shop-player'

function Shop({ run }: { run: Run }) {
  const players = usePlayers()
  const economy = useEconomy(run.id)
  const shop = useShop(run.id)
  const [playerId, setPlayerId] = useState<number | null>(() => {
    try {
      return Number(localStorage.getItem(PLAYER_KEY)) || null
    } catch {
      return null
    }
  })
  const list = players.data ?? []
  const current = list.find((p) => p.id === playerId) ?? list[0]
  useEffect(() => {
    if (!current) return
    try {
      localStorage.setItem(PLAYER_KEY, String(current.id))
    } catch {
      /* per-viewer convenience only */
    }
  }, [current])

  if (players.isLoading || shop.isLoading) return <LoadingState />
  if (!current) return <EmptyState title="Add players in Settings first" />
  const econ = economy.data?.find((e) => e.player_id === current.id)

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-2 text-2xl font-bold text-gold-100">Shop</h1>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Whose shop">
          {list.map((p) => {
            const on = p.id === current.id
            const bal = economy.data?.find((e) => e.player_id === p.id)?.balance
            return (
              <button
                key={p.id}
                aria-pressed={on}
                onClick={() => setPlayerId(p.id)}
                className={`flex items-center gap-2 rounded-full px-3.5 py-1.5 text-sm ring-1 transition ring-inset active:scale-95 ${
                  on ? 'bg-gold-700/50 text-gold-100 ring-gold-400/60' : 'bg-white/5 text-slate-300 ring-slate-700 hover:bg-white/10'
                }`}
              >
                {p.display_name}
                {bal != null && <span className="text-xs text-gold-300 tabular-nums">{bal}</span>}
              </button>
            )
          })}
        </div>
      </div>

      <section className="card flex flex-wrap items-center gap-x-8 gap-y-3">
        <div className="flex flex-col">
          <span className="text-[10px] tracking-[0.15em] text-slate-400 uppercase">{current.display_name}'s gold</span>
          <GoldBadge amount={econ?.balance ?? 0} size="lg" />
        </div>
        <div className="flex gap-6 text-sm">
          <div>
            <div className="font-semibold text-slate-100 tabular-nums">{econ?.earned ?? 0}</div>
            <div className="text-[10px] tracking-[0.12em] text-slate-400 uppercase">Earned</div>
          </div>
          <div>
            <div className="font-semibold text-slate-100 tabular-nums">{econ?.spent ?? 0}</div>
            <div className="text-[10px] tracking-[0.12em] text-slate-400 uppercase">Spent</div>
          </div>
        </div>
        <p className="text-xs text-slate-400 sm:ml-auto sm:max-w-xs">
          Gold comes from kills, assists, damage, vision and multikills in challenge games with Riot data.
        </p>
      </section>

      {run.status !== 'active' && <p className="text-sm text-red-200">This run has ended, so the shop is closed.</p>}
      <ItemGrid run={run} playerId={current.id} balance={econ?.balance ?? 0} items={shop.data?.items ?? []} cap={shop.data?.blacklist_cap ?? 0} />
      <Inventory run={run} playerId={current.id} cap={shop.data?.blacklist_cap ?? 0} />
      <GoldHistory runId={run.id} playerId={current.id} />
    </div>
  )
}

function ItemGrid({
  run,
  playerId,
  balance,
  items,
  cap,
}: {
  run: Run
  playerId: number
  balance: number
  items: ShopItem[]
  cap: number
}) {
  const buy = useAction((type: ItemType) => api.purchase(run.id, playerId, type))
  const [revealed, setRevealed] = useState<ContractInfo | null>(null)
  const sorted = [...items].sort((a, b) => ITEM_ORDER.indexOf(a.type) - ITEM_ORDER.indexOf(b.type))

  return (
    <section className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((item) => {
          const meta = ITEM_META[item.type]
          const short = balance < item.price
          return (
            <div key={item.type} className="card flex flex-col gap-3 p-4">
              <div className="flex items-center gap-3">
                <span
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl ring-1 ring-inset"
                  style={{ background: `${meta.color}22`, color: meta.color, boxShadow: `inset 0 0 0 1px ${meta.color}55` }}
                >
                  <meta.Icon className="h-5 w-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="font-display font-bold text-gold-100">{item.name}</div>
                  <div className="text-xs text-slate-400">{item.when}</div>
                </div>
                <GoldBadge amount={item.price} />
              </div>
              <p className="flex-1 text-sm text-slate-300">
                {item.description}
                {item.type === 'blacklist' && <span className="text-slate-400"> Right now you can ban up to {cap}.</span>}
              </p>
              <button
                className="btn-primary"
                disabled={short || buy.isPending || run.status !== 'active'}
                title={short ? `Need ${item.price - balance} more gold` : undefined}
                onClick={() =>
                  buy.mutate(item.type, { onSuccess: (r) => r.item.contract && setRevealed(r.item.contract) })
                }
              >
                {short ? `Need ${item.price - balance} more` : 'Buy'}
              </button>
            </div>
          )
        })}
      </div>
      <ErrorText error={buy.error} />
      {revealed && <ContractReveal contract={revealed} onClose={() => setRevealed(null)} />}
    </section>
  )
}

const STATUS_LABEL: Record<InventoryItem['status'], string> = {
  unused: 'Ready',
  armed: 'Set for next spin',
  active: 'In play',
  used: 'Used',
  refunded: 'Refunded',
}

function Inventory({ run, playerId, cap }: { run: Run; playerId: number; cap: number }) {
  const inv = useInventory(run.id, playerId)
  const pool = usePool(run.id)
  const champs = useChampionMap()
  const [using, setUsing] = useState<InventoryItem | null>(null)
  const use = useAction(({ id, body }: { id: number; body: Parameters<typeof api.useItem>[1] }) => api.useItem(id, body))
  const alive = useMemo(() => (pool.data ?? []).filter((e) => e.status === 'alive'), [pool.data])
  const items = inv.data ?? []
  const live = items.filter((i) => i.status === 'unused' || i.status === 'armed' || i.status === 'active')
  const past = items.filter((i) => !live.includes(i))

  const describe = (i: InventoryItem) => {
    if (i.type === 'contract' && i.contract) {
      const c = i.contract
      return c.status === 'pending' ? c.description : `${c.description} (${c.status === 'won' ? `won ${c.payout}` : 'missed'})`
    }
    if (i.type === 'shield' && i.target.champion_id) return `On ${champs.get(String(i.target.champion_id))?.name ?? i.target.champion_id}`
    if (i.type === 'blacklist' && Array.isArray(i.target.champion_ids))
      return (i.target.champion_ids as string[]).map((c) => champs.get(c)?.name ?? c).join(', ')
    if (i.status === 'unused' && ['reroll', 'swap', 'choose'].includes(i.type)) return 'Use it on the Wheels tab after a spin'
    return ''
  }

  return (
    <section className="card flex flex-col gap-3">
      <h2 className="text-lg font-bold text-gold-100">Inventory</h2>
      {inv.isLoading && <LoadingState />}
      {inv.isSuccess && items.length === 0 && <p className="text-sm text-slate-400">Nothing yet. Buy something above.</p>}
      <ul className="flex flex-col divide-y divide-white/5">
        {live.map((i) => {
          const meta = ITEM_META[i.type]
          const canUse = i.status === 'unused' && (i.type === 'shield' || i.type === 'blacklist') && run.status === 'active'
          return (
            <li key={i.id} className="flex flex-wrap items-center gap-3 py-2.5">
              <meta.Icon className="h-5 w-5 shrink-0" style={{ color: meta.color }} />
              <span className="font-semibold">{meta.name}</span>
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-300">{STATUS_LABEL[i.status]}</span>
              <span className="min-w-0 flex-1 truncate text-sm text-slate-400">{describe(i)}</span>
              {canUse && (
                <button className="btn-secondary px-3 py-1 text-xs" onClick={() => setUsing(i)}>
                  {i.type === 'shield' ? 'Place shield' : 'Pick champions'}
                </button>
              )}
            </li>
          )
        })}
      </ul>
      {past.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-slate-400">Used items ({past.length})</summary>
          <ul className="mt-2 flex flex-col gap-1.5">
            {past.map((i) => (
              <li key={i.id} className="flex items-center gap-2 text-slate-400">
                <span className="text-slate-300">{ITEM_META[i.type].name}</span>
                {i.used_in_game_id && <span>· game {i.used_in_game_id}</span>}
                <span className="truncate">· {describe(i)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {using?.type === 'shield' && (
        <PickChampionDialog
          title="Place a shield"
          hint="The next time this champion would be eliminated by a loss, the shield breaks instead."
          champions={alive.filter((e) => !e.shield_item_id)}
          busy={use.isPending}
          error={use.error}
          onClose={() => setUsing(null)}
          onPick={(cid) => use.mutate({ id: using.id, body: { champion_id: cid } }, { onSuccess: () => setUsing(null) })}
        />
      )}
      {using?.type === 'blacklist' && (
        <BlacklistDialog
          champions={alive}
          cap={cap}
          busy={use.isPending}
          error={use.error}
          onClose={() => setUsing(null)}
          onConfirm={(ids) => use.mutate({ id: using.id, body: { champion_ids: ids } }, { onSuccess: () => setUsing(null) })}
        />
      )}
    </section>
  )
}

const REASON_LABEL: Record<LedgerRow['reason'], string> = {
  game: 'Game',
  contract_payout: 'Contract',
  purchase: 'Bought',
  refund: 'Refund',
  manual_adjust: 'Adjustment',
}

function GoldHistory({ runId, playerId }: { runId: number; playerId: number }) {
  const gold = useGold(runId, playerId)
  const rows = gold.data?.ledger ?? []
  return (
    <section className="card flex flex-col gap-3">
      <h2 className="text-lg font-bold text-gold-100">Gold history</h2>
      {gold.isSuccess && rows.length === 0 && (
        <p className="text-sm text-slate-400">No gold yet. It comes in after challenge games with Riot data.</p>
      )}
      <ul className="flex flex-col divide-y divide-white/5">
        {rows.map((r) => {
          const b = r.breakdown as Record<string, unknown>
          return (
            <li key={r.id} className={`flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5 text-sm ${r.undone ? 'opacity-40 line-through' : ''}`}>
              <span className={`w-16 font-bold tabular-nums ${r.amount >= 0 ? 'text-gold-300' : 'text-red-300'}`}>{signedGold(r.amount)}</span>
              <span className="font-semibold text-slate-200">
                {REASON_LABEL[r.reason]}
                {r.game_id && <span className="font-normal text-slate-400"> · game {r.game_id}</span>}
              </span>
              {r.reason === 'game' && (
                <span className="flex flex-wrap gap-1.5 text-xs text-slate-400">
                  <Chip label="Kills" value={b.kills} />
                  <Chip label="Assists" value={b.assists} />
                  <Chip label={b.support_bonus ? 'Dmg + heal/shield' : 'Damage'} value={b.damage} />
                  <Chip label="Vision" value={b.vision} />
                  {Number(b.multikills) > 0 && <Chip label="Multikills" value={b.multikills} />}
                  {typeof b.grade === 'string' && <span className="rounded-full bg-hex-800/60 px-2 py-0.5 text-hex-100">{b.grade}</span>}
                </span>
              )}
              {r.reason === 'contract_payout' && typeof b.goal === 'string' && <span className="text-xs text-slate-400">{b.goal}</span>}
              {r.reason === 'purchase' && typeof b.item === 'string' && (
                <span className="text-xs text-slate-400">{ITEM_META[b.item as ItemType]?.name}</span>
              )}
              {r.reason === 'manual_adjust' && typeof b.note === 'string' && b.note && <span className="text-xs text-slate-400">{b.note}</span>}
              <span className="ml-auto text-xs text-slate-500">{new Date(r.created_at).toLocaleDateString()}</span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Chip({ label, value }: { label: string; value: unknown }) {
  return (
    <span className="rounded-full bg-white/5 px-2 py-0.5">
      {label} <span className="text-slate-200 tabular-nums">{String(value ?? 0)}</span>
    </span>
  )
}
