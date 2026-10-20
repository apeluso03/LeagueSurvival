import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorText } from '../components/ui'
import { useAction, usePlayers } from '../hooks/queries'
import { useAccess, useSession } from '../hooks/useAuth'
import { teamColor } from '../lib/teams'
import type { Account, Invite, Player } from '../types'

function Section({ id, title, children }: { id?: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="card flex scroll-mt-32 flex-col gap-4">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  )
}

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : 'never')

/** Your account: who you are, your team colour, password, sign out. Everyone sees this. */
export function AccountSection({ colorPicker }: { colorPicker?: ReactNode }) {
  const { user, isOwner, isSiteAdmin, group, myPlayerId } = useAccess()
  const players = usePlayers()
  const { signedIn, logout } = useSession()
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [mismatch, setMismatch] = useState(false)
  const [saved, setSaved] = useState(false)
  const change = useAction(api.changePassword)
  if (!user) return null
  const player = players.data?.find((p) => p.id === myPlayerId)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setSaved(false)
    setMismatch(next !== confirm)
    if (next !== confirm) return
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: (me) => {
          signedIn(me)
          setCurrent('')
          setNext('')
          setConfirm('')
          setSaved(true)
        },
      },
    )
  }

  return (
    <Section id="account" title="Your account">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <span>
          <span className="text-slate-400">Username </span>
          <b className="text-slate-100">{user.username}</b>
        </span>
        <span className="flex items-center gap-2">
          <span className="text-slate-400">Plays as </span>
          {player ? (
            <>
              <b style={{ color: teamColor(player.id) }}>{player.display_name}</b>
              {colorPicker}
            </>
          ) : (
            <span className="text-slate-300">nobody</span>
          )}
        </span>
        {group && (
          <span>
            <span className="text-slate-400">Group </span>
            <b className="text-slate-100">{group.name}</b>
          </span>
        )}
        {isOwner && <span className="user-chip-role">Group owner</span>}
        {isSiteAdmin && <span className="user-chip-role">Site admin</span>}
      </div>
      <form onSubmit={submit} className="flex flex-col gap-2">
        <span className="text-xs font-semibold tracking-[0.1em] text-slate-300 uppercase">Change password</span>
        <div className="flex flex-wrap gap-2">
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            placeholder="Current password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            placeholder="New password (8+ characters)"
            required
            minLength={8}
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            placeholder="New password again"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
          <button className="btn-primary" disabled={change.isPending}>
            Save
          </button>
        </div>
        {mismatch && <ErrorText error="The new passwords don't match" />}
        <ErrorText error={change.error} />
        {saved && <p className="text-sm text-emerald-300">Password changed. Your other devices were signed out.</p>}
      </form>
      <button
        className="btn-secondary self-start"
        disabled={logout.isPending}
        onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/login', { replace: true }) })}
      >
        Sign out
      </button>
    </Section>
  )
}

/** Site owner: invite links for each player, and who has signed up. */
export function AccountsAdminSection() {
  const { user } = useAccess()
  const players = usePlayers()
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: api.accounts })
  // Links are only shown right after they're made: the server keeps just a hash of each.
  const [links, setLinks] = useState<Record<number, string>>({})
  const makeInvite = useAction(api.createInvite)
  const revoke = useAction(api.revokeInvite)
  const remove = useAction(api.deleteAccount)

  const byPlayer = new Map((accounts.data?.accounts ?? []).filter((a) => a.player_id != null).map((a) => [a.player_id!, a]))
  const invites = new Map((accounts.data?.invites ?? []).map((i) => [i.player_id, i]))
  const unlinked = (accounts.data?.accounts ?? []).filter((a) => a.player_id == null)
  const invite = (pid: number) =>
    makeInvite.mutate(pid, { onSuccess: (inv) => setLinks((l) => ({ ...l, [pid]: `${window.location.origin}/invite/${inv.token}` })) })

  return (
    <Section id="accounts" title="Accounts and invites">
      <GroupName />
      <p className="text-sm text-slate-400">
        Send each friend an invite link for their player. New friends make a username and password; friends who already
        have an account can join with it. They handle their own gold, shop and items, and you can still do everything for
        everyone. Links work once and expire after 7 days. Lost password? Remove them from the group and send a new link;
        their games, gold and items stay.
      </p>
      <ul className="flex flex-col divide-y divide-slate-800">
        {players.data?.map((p) => (
          <AccountRow
            key={p.id}
            player={p}
            account={byPlayer.get(p.id)}
            invite={invites.get(p.id)}
            link={links[p.id]}
            isMe={byPlayer.get(p.id)?.id === user?.id}
            busy={makeInvite.isPending || revoke.isPending || remove.isPending}
            onInvite={() => invite(p.id)}
            onRevoke={(id) =>
              revoke.mutate(id, { onSuccess: () => setLinks(({ [p.id]: _, ...rest }) => rest) })
            }
            onRemove={(a) => confirm(`Remove ${a.username} from the group? ${p.display_name}'s history stays.`) && remove.mutate(a.id)}
          />
        ))}
      </ul>
      {unlinked.length > 0 && (
        <p className="text-xs text-slate-400">
          Members not playing as anyone: {unlinked.map((a) => `${a.username}${a.id === user?.id ? ' (you)' : ''}`).join(', ')}
        </p>
      )}
      <ErrorText error={accounts.error ?? makeInvite.error ?? revoke.error ?? remove.error} />
    </Section>
  )
}

function AccountRow({
  player,
  account,
  invite,
  link,
  isMe,
  busy,
  onInvite,
  onRevoke,
  onRemove,
}: {
  player: Player
  account: Account | undefined
  invite: Invite | undefined
  link: string | undefined
  isMe: boolean
  busy: boolean
  onInvite: () => void
  onRevoke: (inviteId: number) => void
  onRemove: (a: Account) => void
}) {
  const [copied, setCopied] = useState(false)
  const copy = () =>
    void navigator.clipboard?.writeText(link!).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })

  return (
    <li className="flex flex-col gap-2 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="h-3 w-3 rounded-sm" style={{ background: teamColor(player.id) }} aria-hidden />
        <b className="min-w-24">{player.display_name}</b>
        {account ? (
          <>
            <span className="text-sm text-emerald-300">
              @{account.username}
              {isMe && ' (you)'}
            </span>
            <span className="text-xs text-slate-500">last signed in {when(account.last_login_at)}</span>
            {!isMe && (
              <button className="btn-secondary ml-auto px-3 py-1 text-xs" disabled={busy} onClick={() => onRemove(account)}>
                Remove from group
              </button>
            )}
          </>
        ) : (
          <>
            <span className="text-sm text-slate-400">
              {invite ? `Invite sent · expires ${when(invite.expires_at)}` : 'No account yet'}
            </span>
            <span className="ml-auto flex gap-2">
              {invite && (
                <button className="btn-secondary px-3 py-1 text-xs" disabled={busy} onClick={() => onRevoke(invite.id)}>
                  Cancel invite
                </button>
              )}
              <button className="btn-primary px-3 py-1 text-xs" disabled={busy} onClick={onInvite}>
                {invite ? 'New link' : 'Invite link'}
              </button>
            </span>
          </>
        )}
      </div>
      {link && !account && (
        <div className="flex flex-wrap items-center gap-2 pl-6">
          <code className="max-w-full truncate rounded-sm bg-black/50 px-3 py-1.5 text-xs text-hex-200">{link}</code>
          <button className="btn-secondary px-3 py-1 text-xs" onClick={copy}>
            {copied ? 'Copied!' : 'Copy'}
          </button>
          <span className="text-[11px] text-slate-500">Send it to {player.display_name} only. It won't be shown again.</span>
        </div>
      )}
    </li>
  )
}

/** The group owner renames the group. */
function GroupName() {
  const { group } = useAccess()
  const { signedIn } = useSession()
  const [name, setName] = useState(group?.name ?? '')
  const rename = useMutation({ mutationFn: api.renameGroup, onSuccess: (me) => signedIn(me) })
  if (!group) return null
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        rename.mutate(name)
      }}
    >
      <span className="text-xs font-semibold tracking-[0.1em] text-slate-300 uppercase">Group name</span>
      <input className="input" value={name} maxLength={40} onChange={(e) => setName(e.target.value)} />
      <button className="btn-secondary" disabled={rename.isPending || name.trim() === group.name}>
        Rename
      </button>
      <ErrorText error={rename.error} />
    </form>
  )
}

/** Site admin: who can start a group (invite codes, or open sign-up). */
export function SiteSection() {
  const site = useQuery({ queryKey: ['site'], queryFn: api.site })
  const update = useAction(api.updateSite)
  const makeCode = useAction(api.createSiteInvite)
  const revoke = useAction(api.revokeSiteInvite)
  const [note, setNote] = useState('')
  const [made, setMade] = useState<{ note: string; link: string }[]>([])
  const [copied, setCopied] = useState<string | null>(null)
  const s = site.data
  const copy = (text: string) =>
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(text)
      setTimeout(() => setCopied(null), 1500)
    })

  return (
    <Section id="site" title="Site (admin)">
      {s && (
        <p className="text-sm text-slate-400">
          {s.groups} {s.groups === 1 ? 'group' : 'groups'} · {s.users} {s.users === 1 ? 'account' : 'accounts'}
        </p>
      )}
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={!!s?.open_signup}
          disabled={!s || update.isPending}
          onChange={(e) => update.mutate({ open_signup: e.target.checked })}
        />
        <span>
          <b className="text-slate-100">Open sign-up</b>
          <span className="text-slate-400">
            {' '}
            · anyone can start a group without a code. Keep this off until your Riot production key is approved.
          </span>
        </span>
      </label>
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          makeCode.mutate(note, {
            onSuccess: (inv) => {
              setMade((m) => [{ note: inv.note, link: `${window.location.origin}/signup?code=${inv.code}` }, ...m])
              setNote('')
            },
          })
        }}
      >
        <span className="text-xs font-semibold tracking-[0.1em] text-slate-300 uppercase">New group invite</span>
        <input className="input" placeholder="Who it's for (optional)" value={note} maxLength={80} onChange={(e) => setNote(e.target.value)} />
        <button className="btn-primary" disabled={makeCode.isPending}>
          Make invite link
        </button>
      </form>
      {made.map((m) => (
        <div key={m.link} className="flex flex-wrap items-center gap-2">
          <code className="max-w-full truncate rounded-sm bg-black/50 px-3 py-1.5 text-xs text-hex-200">{m.link}</code>
          <button className="btn-secondary px-3 py-1 text-xs" onClick={() => copy(m.link)}>
            {copied === m.link ? 'Copied!' : 'Copy'}
          </button>
          <span className="text-[11px] text-slate-500">
            {m.note ? `For ${m.note}. ` : ''}One use, 30 days. It won't be shown again.
          </span>
        </div>
      ))}
      {!!s?.invites.length && (
        <ul className="flex flex-col divide-y divide-slate-800 text-sm">
          {s.invites.map((i) => (
            <li key={i.id} className="flex items-center gap-3 py-1.5">
              <span className="text-slate-300">{i.note || 'Group invite'}</span>
              <span className="text-xs text-slate-500">expires {when(i.expires_at)}</span>
              <button className="btn-secondary ml-auto px-3 py-1 text-xs" disabled={revoke.isPending} onClick={() => revoke.mutate(i.id)}>
                Cancel
              </button>
            </li>
          ))}
        </ul>
      )}
      <ErrorText error={site.error ?? update.error ?? makeCode.error ?? revoke.error} />
    </Section>
  )
}
