import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ContractReveal } from '../components/ContractReveal'
import { BlacklistDialog, PickChampionDialog } from '../components/ItemDialogs'
import { ItemArt } from '../components/ItemArt'
import { CoinIcon, ShieldIcon } from '../components/icons'
import { ChampionPortrait, EmptyState, ErrorText, LoadingState } from '../components/ui'
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
import { useCountUp } from '../hooks/useCountUp'
import { ITEM_META, ITEM_ORDER, signedGold } from '../lib/items'
import { playPurchase, unlock } from '../lib/sound'
import type { ContractInfo, InventoryItem, ItemType, LedgerRow, PlayerEconomy, Run, ShopItem } from '../types'

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

/** Item categories, like the in-game shop's sidebar. */
const CATEGORIES: { id: string; label: string; types: ItemType[] }[] = [
  { id: 'all', label: 'All items', types: ITEM_ORDER },
  { id: 'spin', label: 'After the spin', types: ['reroll', 'swap', 'choose'] },
  { id: 'prep', label: 'Before the spin', types: ['blacklist', 'contract'] },
  { id: 'protect', label: 'Protection', types: ['shield'] },
]

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
  if (!current || !shop.data) return <EmptyState title="Add players in Settings first" />
  const econ = economy.data?.find((e) => e.player_id === current.id)

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-2 text-2xl font-bold text-gold-100">Shop</h1>
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Whose shop">
          {list.map((p) => {
            const on = p.id === current.id
            const bal = economy.data?.find((e) => e.player_id === p.id)?.balance
            return (
              <button
                key={p.id}
                role="tab"
                aria-selected={on}
                onClick={() => setPlayerId(p.id)}
                className={`flex items-center gap-2 rounded-full px-3.5 py-1.5 text-sm ring-1 transition ring-inset active:scale-95 ${
                  on ? 'bg-gold-700/50 text-gold-100 ring-gold-400/60' : 'bg-white/5 text-slate-300 ring-slate-700 hover:bg-white/10'
                }`}
              >
                {p.display_name}
                {bal != null && (
                  <span className="flex items-center gap-0.5 text-xs text-gold-300 tabular-nums">
                    <CoinIcon className="h-3 w-3" />
                    {bal.toLocaleString()}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {run.status !== 'active' && <p className="text-sm text-red-200">This run has ended, so the shop is closed.</p>}
      <ShopWindow
        key={current.id}
        run={run}
        playerId={current.id}
        playerName={current.display_name}
        econ={econ}
        items={shop.data.items}
        cap={shop.data.blacklist_cap}
      />
      <InPlay run={run} playerId={current.id} />
      <GoldHistory runId={run.id} playerId={current.id} />
    </div>
  )
}

function ShopWindow({
  run,
  playerId,
  playerName,
  econ,
  items,
  cap,
}: {
  run: Run
  playerId: number
  playerName: string
  econ: PlayerEconomy | undefined
  items: ShopItem[]
  cap: number
}) {
  const [category, setCategory] = useState('all')
  const [selected, setSelected] = useState<ItemType>('reroll')
  const [revealed, setRevealed] = useState<ContractInfo | null>(null)
  const [lastBought, setLastBought] = useState<{ type: ItemType; at: number } | null>(null)
  const buy = useAction((type: ItemType) => api.purchase(run.id, playerId, type))
  const balance = econ?.balance ?? 0
  const shownGold = useCountUp(balance)
  const open = run.status === 'active'
  const byType = new Map(items.map((i) => [i.type, i]))
  const types = CATEGORIES.find((c) => c.id === category)!.types.filter((t) => byType.has(t))
  const item = byType.get(selected)!
  const owned = (t: ItemType) => econ?.unused[t] ?? 0

  const purchase = (type: ItemType) => {
    const it = byType.get(type)
    if (!open || !it || balance < it.price || buy.isPending) return
    unlock()
    buy.mutate(type, {
      onSuccess: (r) => {
        playPurchase()
        setLastBought({ type, at: Date.now() })
        if (r.item.contract) setRevealed(r.item.contract)
      },
    })
  }

  return (
    <section className="lol-frame overflow-hidden" aria-label={`${playerName}'s shop`}>
      <div className="lol-frame-title flex items-center justify-between gap-3 px-5 pt-4 pb-3">
        <h2 className="font-display text-lg font-bold tracking-[0.2em] text-gold-200 uppercase">Item Shop</h2>
        <span className="hidden text-xs text-slate-400 sm:inline">Click an item to see it · double-click to buy</span>
      </div>

      <div className="grid gap-0 lg:grid-cols-[170px_1fr_320px]">
        {/* categories */}
        <nav className="flex gap-1 overflow-x-auto border-gold-700/30 p-3 lg:flex-col lg:border-r" aria-label="Categories">
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              aria-pressed={category === c.id}
              onClick={() => setCategory(c.id)}
              className={`rounded-lg px-3 py-2 text-left text-sm whitespace-nowrap transition ${
                category === c.id
                  ? 'bg-gradient-to-r from-gold-700/50 to-transparent text-gold-100 shadow-[inset_2px_0_0_#c8aa6e]'
                  : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
              }`}
            >
              {c.label}
            </button>
          ))}
        </nav>

        {/* item grid */}
        <div className="lol-grid-bg min-h-[260px] p-4" role="listbox" aria-label="Items">
          <div className="grid grid-cols-[repeat(auto-fill,minmax(88px,1fr))] gap-x-2 gap-y-4">
            {types.map((t) => {
              const it = byType.get(t)!
              const broke = balance < it.price
              return (
                <button
                  key={t}
                  role="option"
                  aria-selected={selected === t}
                  title={`${it.name} · ${it.price} gold`}
                  onClick={() => setSelected(t)}
                  onDoubleClick={() => purchase(t)}
                  className={`item-tile flex flex-col items-center gap-1.5 rounded-xl p-1 ${broke ? 'is-broke' : ''}`}
                >
                  <span className="relative">
                    <ItemArt type={t} size={64} />
                    {owned(t) > 0 && (
                      <span className="absolute -right-1.5 -bottom-1.5 min-w-5 rounded-md bg-[#05070b] px-1 text-center text-[11px] font-bold text-gold-100 ring-1 ring-gold-500/70">
                        {owned(t)}
                      </span>
                    )}
                  </span>
                  <span className={`flex items-center gap-1 text-sm font-bold tabular-nums ${broke ? 'text-red-400' : 'text-gold-300'}`}>
                    <CoinIcon className="h-3.5 w-3.5" />
                    {it.price.toLocaleString()}
                  </span>
                  <span className="w-full truncate text-center text-[11px] text-slate-400">{it.name}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* details */}
        <aside className="flex flex-col gap-3 border-gold-700/30 bg-black/20 p-5 lg:border-l" aria-live="polite">
          <div className="flex items-center gap-4">
            <ItemArt type={item.type} size={76} />
            <div className="min-w-0">
              <div className="font-display text-lg leading-tight font-bold text-gold-100">{item.name}</div>
              <div className={`mt-1 flex items-center gap-1 font-bold tabular-nums ${balance < item.price ? 'text-red-400' : 'text-gold-300'}`}>
                <CoinIcon className="h-4 w-4" />
                {item.price.toLocaleString()}
              </div>
            </div>
          </div>
          <div className="h-px bg-gradient-to-r from-gold-700/60 to-transparent" />
          <p className="text-xs tracking-[0.12em] text-hex-200 uppercase">{item.when}</p>
          <p className="text-sm leading-relaxed text-slate-200">{item.description}</p>
          {item.type === 'blacklist' && <p className="text-sm text-slate-400">Right now you can ban up to {cap} champions.</p>}
          {item.type === 'contract' && <p className="text-sm text-slate-400">Hit the goal and it pays out bonus gold.</p>}
          {owned(item.type) > 0 && <p className="text-sm text-gold-200">You own {owned(item.type)} ready to use.</p>}
          <div className="mt-auto flex flex-col gap-2 pt-2">
            <button className="btn-hextech" disabled={!open || balance < item.price || buy.isPending} onClick={() => purchase(item.type)}>
              {buy.isPending ? 'Buying...' : balance < item.price ? `Need ${(item.price - balance).toLocaleString()} more` : 'Purchase'}
            </button>
            <ErrorText error={buy.error} />
          </div>
        </aside>
      </div>

      {/* inventory bar + gold, like the in-game HUD */}
      <InventoryBar run={run} playerId={playerId} econ={econ} cap={cap} lastBought={lastBought} gold={shownGold} />
      {revealed && <ContractReveal contract={revealed} playerName={playerName} onClose={() => setRevealed(null)} />}
    </section>
  )
}

function InventoryBar({
  run,
  playerId,
  econ,
  cap,
  lastBought,
  gold,
}: {
  run: Run
  playerId: number
  econ: PlayerEconomy | undefined
  cap: number
  lastBought: { type: ItemType; at: number } | null
  gold: number
}) {
  const inv = useInventory(run.id, playerId)
  const pool = usePool(run.id)
  const [using, setUsing] = useState<InventoryItem | null>(null)
  const use = useAction(({ id, body }: { id: number; body: Parameters<typeof api.useItem>[1] }) => api.useItem(id, body))
  const alive = useMemo(() => (pool.data ?? []).filter((e) => e.status === 'alive'), [pool.data])
  const items = inv.data ?? []
  const unusedOf = (t: ItemType) => items.find((i) => i.type === t && i.status === 'unused')

  const slotAction = (t: ItemType) => {
    const it = unusedOf(t)
    if (!it || run.status !== 'active') return
    if (t === 'shield' || t === 'blacklist') setUsing(it)
  }
  const hint = (t: ItemType, n: number) => {
    if (!n) return ITEM_META[t].name
    if (t === 'shield') return 'Click to place a shield'
    if (t === 'blacklist') return 'Click to pick champions to ban'
    if (t === 'contract') return 'Contracts start as soon as they are bought'
    return 'Use it on the Wheels tab after a spin'
  }

  return (
    <div className="flex flex-wrap items-center gap-4 border-t border-gold-700/40 bg-black/30 px-4 py-4 sm:px-5">
      <div className="flex gap-1.5 sm:gap-2" aria-label="Inventory">
        {ITEM_ORDER.map((t) => {
          const n = econ?.unused[t] ?? 0
          const clickable = n > 0 && (t === 'shield' || t === 'blacklist') && run.status === 'active'
          const popped = lastBought?.type === t
          return (
            <button
              key={t}
              title={hint(t, n)}
              onClick={() => slotAction(t)}
              disabled={!clickable}
              className={`inv-slot relative grid h-[46px] w-[46px] place-items-center sm:h-14 sm:w-14 ${clickable ? 'cursor-pointer hover:brightness-125' : 'cursor-default'}`}
            >
              {n > 0 ? (
                <span key={popped ? lastBought!.at : 'idle'} className={popped ? 'slot-pop' : ''}>
                  <ItemArt type={t} size={40} className="sm:scale-[1.2]" />
                </span>
              ) : (
                <span className="opacity-15">
                  <ItemArt type={t} size={40} className="sm:scale-[1.2]" />
                </span>
              )}
              {n > 1 && (
                <span className="absolute right-0.5 bottom-0 text-[11px] font-bold text-gold-100 [text-shadow:0_1px_2px_#000]">{n}</span>
              )}
              {t === 'blacklist' && econ?.armed_blacklist && (
                <span className="absolute -top-1.5 left-1/2 -translate-x-1/2 rounded bg-red-700 px-1 text-[9px] font-bold text-white uppercase">armed</span>
              )}
              {t === 'contract' && econ?.active_contract && (
                <span className="absolute -top-1.5 left-1/2 -translate-x-1/2 rounded bg-gold-600 px-1 text-[9px] font-bold text-slate-950 uppercase">live</span>
              )}
            </button>
          )
        })}
      </div>
      <div className="ml-auto flex items-center gap-3 rounded-xl bg-[#05070b] px-4 py-2 ring-1 ring-gold-700/60 ring-inset">
        <CoinIcon className="h-7 w-7" />
        <div className="flex flex-col leading-tight">
          <span className="font-display text-2xl font-bold text-gold-200 tabular-nums">{gold.toLocaleString()}</span>
          <span className="text-[10px] tracking-[0.12em] text-slate-400 uppercase">
            earned {(econ?.earned ?? 0).toLocaleString()} · spent {(econ?.spent ?? 0).toLocaleString()}
          </span>
        </div>
      </div>

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
    </div>
  )
}

/** What this player has working right now: placed shields, an armed blacklist, live contracts. */
function InPlay({ run, playerId }: { run: Run; playerId: number }) {
  const inv = useInventory(run.id, playerId)
  const champs = useChampionMap()
  const items = inv.data ?? []
  const shields = items.filter((i) => i.type === 'shield' && i.status === 'active')
  const blacklist = items.find((i) => i.type === 'blacklist' && i.status === 'armed')
  const contracts = items.filter((i) => i.type === 'contract' && i.status === 'active' && i.contract)
  const past = items.filter((i) => i.status === 'used' || i.status === 'refunded')
  if (!shields.length && !blacklist && !contracts.length && !past.length) return null

  return (
    <section className="card flex flex-col gap-4">
      <h2 className="text-lg font-bold text-gold-100">In play</h2>
      {shields.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="flex items-center gap-1.5 text-emerald-300">
            <ShieldIcon className="h-4 w-4" /> Shielding
          </span>
          {shields.map((s) => {
            const c = champs.get(String(s.target.champion_id))
            return (
              <span key={s.id} className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 py-0.5 pr-2.5 pl-0.5 ring-1 ring-emerald-500/30 ring-inset">
                <ChampionPortrait champion={c} size="xs" className="rounded-full" />
                {c?.name}
              </span>
            )
          })}
        </div>
      )}
      {blacklist && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-red-300">Banned from the next spin:</span>
          {(blacklist.target.champion_ids as string[]).map((cid) => (
            <span key={cid} className="flex items-center gap-1.5 rounded-full bg-red-500/10 py-0.5 pr-2.5 pl-0.5 ring-1 ring-red-500/30 ring-inset">
              <ChampionPortrait champion={champs.get(cid)} size="xs" className="rounded-full" dim />
              {champs.get(cid)?.name}
            </span>
          ))}
        </div>
      )}
      {contracts.map((c) => (
        <p key={c.id} className="text-sm text-gold-200">
          Contract: {c.contract!.description} <span className="text-slate-400">(pays {c.contract!.payout})</span>
        </p>
      ))}
      {past.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-slate-400">Used items ({past.length})</summary>
          <ul className="mt-2 flex flex-col gap-1.5">
            {past.map((i) => (
              <li key={i.id} className="flex items-center gap-2 text-slate-400">
                <ItemArt type={i.type} size={22} />
                <span className="text-slate-300">{ITEM_META[i.type].name}</span>
                {i.used_in_game_id && <span>· game {i.used_in_game_id}</span>}
                {i.contract && <span>· {i.contract.description} ({i.contract.status === 'won' ? `won ${i.contract.payout}` : 'missed'})</span>}
              </li>
            ))}
          </ul>
        </details>
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
                <span className="flex items-center gap-1.5 text-xs text-slate-400">
                  <ItemArt type={b.item as ItemType} size={18} />
                  {ITEM_META[b.item as ItemType]?.name}
                </span>
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
