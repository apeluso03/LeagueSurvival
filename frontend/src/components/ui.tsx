import { useEffect, type ReactNode } from 'react'
import type { Champion } from '../types'

const SIZES = { xs: 'h-7 w-7', sm: 'h-10 w-10', md: 'h-14 w-14', lg: 'h-20 w-20', mdlg: 'h-14 w-14 sm:h-20 sm:w-20' }

export function ChampionPortrait({
  champion,
  size = 'md',
  dim = false,
  eager = false,
  className = '',
}: {
  champion: Pick<Champion, 'name' | 'image_url'> | undefined
  size?: keyof typeof SIZES
  dim?: boolean
  /** Load right away instead of when scrolled into view (needed inside the spinning reel). */
  eager?: boolean
  className?: string
}) {
  const base = `${SIZES[size]} shrink-0 rounded-md object-cover ${dim ? 'grayscale opacity-40' : ''} ${className}`
  if (!champion?.image_url) {
    return <div className={`${base} bg-slate-800`} title={champion?.name} />
  }
  return <img src={champion.image_url} alt={champion.name} title={champion.name} loading={eager ? 'eager' : 'lazy'} className={base} />
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-4 sm:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-label={title}
        className="card max-h-[85dvh] w-full max-w-lg overflow-y-auto bg-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button className="text-slate-400 hover:text-white" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <p role="alert" className="rounded-md border border-red-900 bg-red-950/60 px-3 py-2 text-sm text-red-200">
      {error instanceof Error ? error.message : String(error)}
    </p>
  )
}

export function Stat({ label, value, accent = false }: { label: string; value: ReactNode; accent?: boolean }) {
  return (
    <div className="flex flex-col items-center leading-tight">
      <span className={`text-lg font-bold ${accent ? 'text-gold-400' : ''}`}>{value}</span>
      <span className="text-[11px] uppercase tracking-wide text-slate-400">{label}</span>
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center gap-3 py-10 text-center">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </div>
  )
}

export function Spinner({ className = '' }: { className?: string }) {
  return (
    <span
      role="progressbar"
      aria-label="Loading"
      className={`inline-block h-5 w-5 animate-spin rounded-full border-2 border-slate-600 border-t-gold-400 ${className}`}
    />
  )
}

export function LoadingState({ label = 'Loading...' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-16 text-sm text-slate-400">
      <Spinner />
      {label}
    </div>
  )
}
