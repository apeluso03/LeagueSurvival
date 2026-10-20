import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { usePlayerMap } from '../hooks/queries'
import { useAccess, useSession } from '../hooks/useAuth'
import { teamColor } from '../lib/teams'

/** Who's signed in and in which group: switch groups, start or join one, account, sign out. */
export function UserMenu() {
  const { user, group, groups, isOwner } = useAccess()
  const players = usePlayerMap()
  const { logout, signedIn } = useSession()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [switching, setSwitching] = useState(false)
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
  const playerId = group?.player_id ?? null
  const player = playerId != null ? players.get(playerId) : undefined
  const color = playerId != null ? teamColor(playerId) : '#2e9bff'

  const switchTo = async (id: number) => {
    setSwitching(true)
    try {
      signedIn(await api.switchGroup(id)) // a fresh start: another group's data
      setOpen(false)
      navigate('/', { replace: true })
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="user-chip"
        style={{ ['--team' as string]: color }}
        title={`Signed in as ${user.username}${group ? ` · ${group.name}` : ''}`}
      >
        <span className="user-chip-dot" aria-hidden />
        <span className="max-w-28 truncate">{player?.display_name ?? user.username}</span>
        {isOwner && <span className="user-chip-role">Owner</span>}
      </button>
      {open && (
        <div role="menu" className="user-menu fade-in">
          <div className="border-b border-white/8 px-3 pt-2 pb-2.5">
            <div className="text-[10px] tracking-[0.15em] text-slate-500 uppercase">Signed in as</div>
            <div className="truncate font-semibold text-slate-100">{user.username}</div>
            {group && (
              <div className="text-[11px] text-slate-400">
                {group.name} · {isOwner ? 'owner' : player ? `plays as ${player.display_name}` : 'member'}
              </div>
            )}
          </div>
          {groups.length > 1 && (
            <div className="border-b border-white/8 py-1">
              <div className="px-3 pt-1 text-[10px] tracking-[0.15em] text-slate-500 uppercase">Your groups</div>
              {groups.map((g) => (
                <button
                  key={g.id}
                  role="menuitemradio"
                  aria-checked={g.id === group?.id}
                  disabled={switching || g.id === group?.id}
                  className="user-menu-item w-full text-left"
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
                  onClick={() => void switchTo(g.id)}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${g.id === group?.id ? 'bg-hex-300' : 'bg-transparent'}`} />
                  <span className="truncate">{g.name}</span>
                  {g.role === 'owner' && <span className="ml-auto text-[10px] text-gold-300">owner</span>}
                </button>
              ))}
            </div>
          )}
          {player && (
            <Link role="menuitem" to={`/players/${player.id}`} className="user-menu-item" onClick={() => setOpen(false)}>
              My player page
            </Link>
          )}
          <Link role="menuitem" to="/groups/new" className="user-menu-item" onClick={() => setOpen(false)}>
            Start a group
          </Link>
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
