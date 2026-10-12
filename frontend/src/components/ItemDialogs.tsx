import { useState } from 'react'
import { filterChampions } from '../lib/champions'
import { ITEM_META } from '../lib/items'
import type { Player, PoolEntry } from '../types'
import { ChampionPortrait, ErrorText, Modal } from './ui'

type Pickable = Pick<PoolEntry, 'champion_id' | 'name' | 'image_url' | 'tags'>

function Grid({
  champions,
  selected,
  onToggle,
}: {
  champions: Pickable[]
  selected: Set<string>
  onToggle: (id: string) => void
}) {
  const [search, setSearch] = useState('')
  const shown = filterChampions(champions, search)
  return (
    <div className="flex flex-col gap-3">
      <input autoFocus className="input" placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} />
      <div className="grid max-h-[50dvh] grid-cols-4 gap-2 overflow-y-auto sm:grid-cols-6">
        {shown.map((c) => {
          const on = selected.has(c.champion_id)
          return (
            <button
              key={c.champion_id}
              onClick={() => onToggle(c.champion_id)}
              aria-pressed={on}
              className={`flex flex-col items-center gap-1 rounded-2xl p-1 transition active:scale-95 ${
                on ? 'bg-gold-500/15 ring-2 ring-gold-400 ring-inset' : 'hover:bg-white/5'
              }`}
            >
              <ChampionPortrait champion={c} size="md" className="rounded-xl" />
              <span className="w-full truncate text-center text-[11px]">{c.name}</span>
            </button>
          )
        })}
        {shown.length === 0 && <p className="col-span-full text-sm text-slate-400">No champions match.</p>}
      </div>
    </div>
  )
}

/** Pick one champion (Shield, Choose a Champ). */
export function PickChampionDialog({
  title,
  hint,
  champions,
  onPick,
  onClose,
  busy,
  error,
}: {
  title: string
  hint?: string
  champions: Pickable[]
  onPick: (championId: string) => void
  onClose: () => void
  busy?: boolean
  error?: unknown
}) {
  return (
    <Modal title={title} onClose={onClose}>
      {hint && <p className="mb-3 text-sm text-slate-400">{hint}</p>}
      <Grid champions={champions} selected={new Set()} onToggle={(id) => !busy && onPick(id)} />
      <div className="mt-3">
        <ErrorText error={error} />
      </div>
    </Modal>
  )
}

/** Pick up to `cap` champions (Blacklist). */
export function BlacklistDialog({
  champions,
  cap,
  onConfirm,
  onClose,
  busy,
  error,
}: {
  champions: Pickable[]
  cap: number
  onConfirm: (ids: string[]) => void
  onClose: () => void
  busy?: boolean
  error?: unknown
}) {
  const [picked, setPicked] = useState<string[]>([])
  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length < cap ? [...p, id] : p))
  return (
    <Modal title="Blacklist champions" onClose={onClose}>
      <p className="mb-3 text-sm text-slate-400">
        Pick up to {cap}. They won't show up in this player's next spin (everyone else can still roll them).
      </p>
      <Grid champions={champions} selected={new Set(picked)} onToggle={toggle} />
      <div className="mt-4 flex items-center justify-between gap-3">
        <span className="text-sm text-slate-300">
          {picked.length} / {cap} picked
        </span>
        <button className="btn-primary" disabled={!picked.length || busy} onClick={() => onConfirm(picked)}>
          Ban for next spin
        </button>
      </div>
      <div className="mt-3">
        <ErrorText error={error} />
      </div>
    </Modal>
  )
}

/** Pick the player to Swap with. */
export function SwapDialog({
  players,
  onPick,
  onClose,
  busy,
  error,
}: {
  players: Player[]
  onPick: (playerId: number) => void
  onClose: () => void
  busy?: boolean
  error?: unknown
}) {
  const Icon = ITEM_META.swap.Icon
  return (
    <Modal title="Swap lists with..." onClose={onClose}>
      <div className="flex flex-col gap-2">
        {players.map((p) => (
          <button key={p.id} className="btn-secondary justify-start" disabled={busy} onClick={() => onPick(p.id)}>
            <Icon className="h-4 w-4" />
            {p.display_name}
          </button>
        ))}
      </div>
      <div className="mt-3">
        <ErrorText error={error} />
      </div>
    </Modal>
  )
}
