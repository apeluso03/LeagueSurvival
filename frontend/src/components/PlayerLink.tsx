import { Link } from 'react-router-dom'
import { usePlayerMap } from '../hooks/queries'

/** A player's name that opens their profile page. */
export function PlayerLink({ id, className = '' }: { id: number; className?: string }) {
  const players = usePlayerMap()
  return (
    <Link
      to={`/players/${id}`}
      className={`underline-offset-2 transition-colors duration-150 hover:text-gold-200 hover:underline ${className}`}
    >
      {players.get(id)?.display_name ?? `Player ${id}`}
    </Link>
  )
}
