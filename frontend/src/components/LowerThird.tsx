import type { CSSProperties, ReactNode } from 'react'
import { usePlayerMap } from '../hooks/queries'
import { teamColor } from '../lib/teams'

/**
 * A player's broadcast name bar: their team colour down the left, the name in the display font,
 * and an optional coloured tag (e.g. a record or "PICK #1").
 */
export function LowerThird({
  playerId,
  name,
  sub,
  size = 'md',
  className = '',
}: {
  playerId: number
  name?: string
  sub?: ReactNode
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  const players = usePlayerMap()
  const label = name ?? players.get(playerId)?.display_name ?? `Player ${playerId}`
  const text = { sm: 'text-xs', md: 'text-sm', lg: 'text-lg' }[size]
  return (
    <span className={`lower-third ${text} ${className}`} style={{ '--team': teamColor(playerId) } as CSSProperties}>
      <span className="lt-name">{label}</span>
      {sub != null && sub !== '' && <span className="lt-sub">{sub}</span>}
    </span>
  )
}
