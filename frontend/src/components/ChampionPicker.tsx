import { useState } from 'react'
import { filterChampions } from '../lib/champions'
import type { Champion } from '../types'
import { ChampionPortrait } from './ui'

/** Searchable champion grid. Used for "other" picks and revive choices. */
export function ChampionPicker({
  champions,
  onPick,
  dim,
}: {
  champions: Champion[]
  onPick: (c: Champion) => void
  dim?: (c: Champion) => boolean
}) {
  const [search, setSearch] = useState('')
  const shown = filterChampions(champions, search)
  return (
    <div className="flex flex-col gap-3">
      <input
        autoFocus
        className="input"
        placeholder="Search champions..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
        {shown.map((c) => (
          <button
            key={c.id}
            onClick={() => onPick(c)}
            className="flex flex-col items-center gap-1 rounded-md p-1 hover:bg-slate-800"
          >
            <ChampionPortrait champion={c} size="md" dim={dim?.(c)} />
            <span className="w-full truncate text-center text-[11px]">{c.name}</span>
          </button>
        ))}
        {shown.length === 0 && <p className="col-span-full text-sm text-slate-400">No champions match.</p>}
      </div>
    </div>
  )
}
