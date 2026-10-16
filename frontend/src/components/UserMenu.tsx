import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { usePlayerMap } from '../hooks/queries'
import { useAccess, useSession } from '../hooks/useAuth'
import { teamColor } from '../lib/teams'

/** Who's signed in, with links to their player page and account, and Sign out. */
export function UserMenu() {
  const { user, isAdmin } = useAccess()
  const players = usePlayerMap()
  const { logout } = useSession()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', close)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', close)
    }
  }, [open])

  if (!user) return null
  const player = user.player_id != null ? players.get(user.player_id) : undefined
  const color = user.player_id != null ? teamColor(user.player_id) : '#2e9bff'

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="user-chip"
        style={{ ['--team' as string]: color }}
        title={`Signed in as ${user.username}`}
      >
        <span className="user-chip-dot" aria-hidden />
        <span className="max-w-28 truncate">{player?.display_name ?? user.username}</span>
        {isAdmin && <span className="user-chip-role">Owner</span>}
      </button>
      {open && (
        <div role="menu" className="user-menu fade-in">
          <div className="border-b border-white/8 px-3 pt-2 pb-2.5">
            <div className="text-[10px] tracking-[0.15em] text-slate-500 uppercase">Signed in as</div>
            <div className="truncate font-semibold text-slate-100">{user.username}</div>
            <div className="text-[11px] text-slate-400">
              {isAdmin ? 'Site owner' : player ? `Plays as ${player.display_name}` : 'Not linked to a player'}
            </div>
          </div>
          {player && (
            <Link role="menuitem" to={`/players/${player.id}`} className="user-menu-item" onClick={() => setOpen(false)}>
              My player page
            </Link>
          )}
          <Link role="menuitem" to="/settings#account" className="user-menu-item" onClick={() => setOpen(false)}>
            Account
          </Link>
          <button
            role="menuitem"
            className="user-menu-item w-full text-left text-red-300"
            disabled={logout.isPending}
            onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/login', { replace: true }) })}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
