import type React from 'react'
import type { ReactNode } from 'react'
import { useChampionMap, usePlayerMap } from '../hooks/queries'
import type { Game } from '../types'
import { teamColor } from '../lib/teams'
import { ChampionPortrait } from './ui'

/** Pinned under the header while a game is pending: who has marked their champion, and who hasn't. */
export function PickBar({ game, extra }: { game: Game; extra?: ReactNode }) {
  const champs = useChampionMap()
  const players = usePlayerMap()
  const done = game.assignments.filter((a) => a.played_champion_id).length
  const all = done === game.assignments.length
  return (
    <div className="pick-bar sticky z-30 -mx-4 border-b border-white/10 bg-[#06080c]/94 px-4 py-2 backdrop-blur sm:mx-0 sm:rounded-sm sm:border sm:px-3">
      <div className="flex items-center gap-2 overflow-x-auto">
        <span className="broadcast-tag shrink-0" style={{ ['--tag' as string]: all ? 'var(--color-hex-400)' : '#454e5e' } as React.CSSProperties}>
          {all ? 'All locked' : `${done}/${game.assignments.length} picked`}
        </span>
        {game.assignments.map((a) => {
          const c = a.played_champion_id ? champs.get(a.played_champion_id) : undefined
          const name = players.get(a.player_id)?.display_name ?? `Player ${a.player_id}`
          return (
            <span
              key={a.player_id}
              className={`pick-chip ${c ? 'is-picked' : ''}`}
              style={{ ['--team' as string]: teamColor(a.player_id) } as React.CSSProperties}
            >
              {c && <ChampionPortrait champion={c} size="xs" className="h-5 w-5 rounded-full" />}
              <b>{name}</b>
              <span className={c ? 'text-white' : 'text-slate-400'}>{c ? c.name : 'picking…'}</span>
            </span>
          )
        })}
        {extra && <div className="ml-auto shrink-0 pl-2">{extra}</div>}
      </div>
    </div>
  )
}
