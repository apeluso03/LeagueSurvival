import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, isUnreachable } from '../api/client'
import { LogoMark } from '../components/icons'
import { LegalNotice } from '../components/LegalNotice'
import { ErrorText, LoadingState } from '../components/ui'
import { useMe, useSession } from '../hooks/useAuth'
import { usePageTitle } from '../hooks/usePageTitle'
import type { Me } from '../types'

const MIN_PASSWORD = 8

/** Sends signed-out visitors to sign in (or, on a brand-new site, to set it up). */
export function RequireAuth() {
  const me = useMe()
  const location = useLocation()
  if (me.isPending) return <LoadingState />
  if (me.isError) {
    return (
      <AuthShell title="Can't connect">
        <p className="text-sm text-slate-300">
          {isUnreachable(me.error) ? "Can't reach the backend. Is it running?" : String(me.error.message)}
        </p>
        <button className="btn-secondary mt-4 w-full" onClick={() => void me.refetch()}>
          Try again
        </button>
      </AuthShell>
    )
  }
  if (!me.data.user) {
    return <Navigate to={me.data.setup_needed ? '/setup' : '/login'} state={{ from: location.pathname }} replace />
  }
  return <Outlet />
}

function AuthShell({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden px-4 py-10">
      <div aria-hidden className="pointer-events-none absolute top-[-14rem] left-1/2 -translate-x-1/2">
        <div className="landing-ring h-[40rem] w-[40rem] rounded-full ring-1 ring-hex-300/15" />
        <div className="absolute inset-40 rounded-full bg-hex-300/[0.06] blur-3xl" />
      </div>
      <div className="page-in relative z-10 flex w-full max-w-sm flex-col items-center">
        <LogoMark className="h-16 w-16" />
        <div className="font-display mt-3 text-sm tracking-[0.2em] uppercase">
          <span className="text-white">Hardcore</span> <span className="blue-text">Draft</span>
        </div>
        <div className="card mt-6 w-full bg-slate-900/80">
          <h1 className="text-xl font-bold text-gold-100">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
          <div className="mt-5">{children}</div>
        </div>
        <LegalNotice className="mt-6" />
      </div>
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold tracking-[0.1em] text-slate-300 uppercase">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-slate-500">{hint}</span>}
    </label>
  )
}

/** Username + password (+ confirm) fields shared by setup and invite sign-up. */
function NewAccountFields({
  username,
  setUsername,
  password,
  setPassword,
  confirm,
  setConfirm,
}: {
  username: string
  setUsername: (v: string) => void
  password: string
  setPassword: (v: string) => void
  confirm: string
  setConfirm: (v: string) => void
}) {
  return (
    <>
      <Field label="Username" hint="3-24 letters, numbers, dots, dashes or underscores">
        <input
          className="input"
          autoComplete="username"
          autoFocus
          required
          minLength={3}
          maxLength={24}
          pattern="[A-Za-z0-9_.\-]+"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </Field>
      <Field label="Password" hint={`At least ${MIN_PASSWORD} characters`}>
        <input
          className="input"
          type="password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <Field label="Confirm password">
        <input
          className="input"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </Field>
    </>
  )
}

/** Where to go once signed in: the page that sent you to sign in, or home. */
function useDestination() {
  const from = (useLocation().state as { from?: string } | null)?.from
  return from && !['/login', '/setup'].includes(from) ? from : '/'
}

function useSignIn<T>(fn: (body: T) => Promise<Me>) {
  const { signedIn } = useSession()
  const navigate = useNavigate()
  const dest = useDestination()
  return useMutation({
    mutationFn: fn,
    onSuccess: (me) => {
      navigate(dest, { replace: true })
      signedIn(me)
    },
  })
}

export function LoginPage() {
  usePageTitle('Sign in')
  const me = useMe()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const login = useSignIn(api.login)
  const dest = useDestination()

  if (me.data?.user) return <Navigate to={dest} replace />
  if (me.data?.setup_needed) return <Navigate to="/setup" replace />

  const submit = (e: FormEvent) => {
    e.preventDefault()
    login.mutate({ username, password })
  }
  return (
    <AuthShell title="Sign in" subtitle="Welcome back, summoner.">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Username">
          <input
            className="input"
            autoComplete="username"
            autoFocus
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </Field>
        <Field label="Password">
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <ErrorText error={login.error} />
        <button type="submit" className="btn-primary w-full py-2.5" disabled={login.isPending}>
          {login.isPending ? 'Signing in...' : 'Sign in'}
        </button>
        <p className="text-center text-xs text-slate-500">
          New here? Ask the owner for an invite link. Forgot your password? The owner can send you a new one.
        </p>
      </form>
    </AuthShell>
  )
}

export function SetupPage() {
  usePageTitle('Set up')
  const me = useMe()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [playerId, setPlayerId] = useState<number | null>(null)
  const [mismatch, setMismatch] = useState(false)
  const setUp = useSignIn(api.setUp)
  const dest = useDestination()

  if (me.data?.user) return <Navigate to={dest} replace />
  if (me.data && !me.data.setup_needed) return <Navigate to="/login" replace />
  if (me.isPending) return <LoadingState />

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setMismatch(password !== confirm)
    if (password === confirm) setUp.mutate({ username, password, player_id: playerId })
  }
  const players = me.data?.players ?? []
  return (
    <AuthShell
      title="Make the owner account"
      subtitle="You're the first one here, so this account runs the site: spins, results, settings, and invites for everyone else."
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <NewAccountFields {...{ username, setUsername, password, setPassword, confirm, setConfirm }} />
        <Field label="Which player are you?" hint="Your own gold, shop and title. You can still manage everyone's.">
          <select
            className="input"
            value={playerId ?? ''}
            onChange={(e) => setPlayerId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">I don't play, I just run it</option>
            {players.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
        </Field>
        {mismatch && <ErrorText error="The passwords don't match" />}
        <ErrorText error={setUp.error} />
        <button type="submit" className="btn-primary w-full py-2.5" disabled={setUp.isPending}>
          {setUp.isPending ? 'Setting up...' : 'Create owner account'}
        </button>
      </form>
    </AuthShell>
  )
}

export function InvitePage() {
  usePageTitle('Join')
  const { token = '' } = useParams()
  const me = useMe()
  const register = useSignIn(api.register)
  // Stop asking about the link once it's been used to sign up (it would answer "already used").
  const invite = useQuery({
    queryKey: ['invite', token],
    queryFn: () => api.invite(token),
    retry: false,
    enabled: !register.isSuccess,
  })
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [mismatch, setMismatch] = useState(false)

  if (invite.isPending) return <LoadingState />
  if (invite.isError) {
    return (
      <AuthShell title="Invite link not working">
        <ErrorText error={invite.error} />
        <Link to="/login" className="btn-secondary mt-4 w-full">
          Go to sign in
        </Link>
      </AuthShell>
    )
  }
  if (me.data?.user) {
    return (
      <AuthShell title="You're already signed in" subtitle={`as ${me.data.user.username}`}>
        <p className="text-sm text-slate-300">
          This link is for whoever plays as <b className="text-gold-100">{invite.data.display_name}</b>. Sign out first
          if that's a new account, or pass the link on.
        </p>
        <Link to="/" className="btn-secondary mt-4 w-full">
          Back to the app
        </Link>
      </AuthShell>
    )
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setMismatch(password !== confirm)
    if (password === confirm) register.mutate({ token, username, password })
  }
  return (
    <AuthShell
      title={`Join as ${invite.data.display_name}`}
      subtitle="Make your account to handle your own gold, shop and items."
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <NewAccountFields {...{ username, setUsername, password, setPassword, confirm, setConfirm }} />
        {mismatch && <ErrorText error="The passwords don't match" />}
        <ErrorText error={register.error} />
        <button type="submit" className="btn-primary w-full py-2.5" disabled={register.isPending}>
          {register.isPending ? 'Joining...' : 'Create account'}
        </button>
        <p className="text-center text-xs text-slate-500">
          Already have an account? <Link to="/login" className="text-hex-200 hover:underline">Sign in</Link>
        </p>
      </form>
    </AuthShell>
  )
}
