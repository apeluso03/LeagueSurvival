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
    <div
      className="fade-in fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-3 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label={title}
        className="card sheet-in max-h-[88dvh] w-full max-w-lg overflow-y-auto bg-slate-900/90"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto -mt-2 mb-3 h-1 w-10 rounded-full bg-slate-600 sm:hidden" aria-hidden />
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-gold-100">{title}</h2>
          <button
            className="grid h-8 w-8 place-items-center rounded-full bg-white/5 text-slate-400 transition hover:bg-white/10 hover:text-white active:scale-90"
            onClick={onClose}
            aria-label="Close"
          >
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
    <p role="alert" className="rounded-2xl bg-red-950/50 px-4 py-2.5 text-sm text-red-200 ring-1 ring-red-800/60 ring-inset">
      {error instanceof Error ? error.message : String(error)}
    </p>
  )
}

export function Stat({ label, value, accent = false }: { label: string; value: ReactNode; accent?: boolean }) {
  return (
    <div className="flex flex-col items-center leading-tight">
      <span className={`text-lg font-bold tabular-nums ${accent ? 'gold-text' : 'text-slate-100'}`}>{value}</span>
      <span className="text-[10px] font-medium tracking-[0.12em] text-slate-400 uppercase">{label}</span>
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
