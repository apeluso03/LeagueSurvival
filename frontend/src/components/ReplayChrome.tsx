import type { CSSProperties, ReactNode } from 'react'

/** Letterbox bars and a broadcast tag ("REPLAY · GAME 19") around a full-screen moment. */
export function ReplayChrome({ tag, color = '#e5283c' }: { tag: ReactNode; color?: string }) {
  return (
    <>
      <div className="replay-bar replay-bar-top" aria-hidden />
      <div className="replay-bar replay-bar-bottom" aria-hidden />
      <span className="replay-tag broadcast-tag" style={{ '--tag': color } as CSSProperties}>
        <span className="live-dot" /> {tag}
      </span>
    </>
  )
}

/** A slanted colour band that wipes in behind a big title. */
export function BroadcastBanner({ color, children, className = '' }: { color: string; children: ReactNode; className?: string }) {
  return (
    <div className={`broadcast-banner ${className}`} style={{ '--banner': color } as CSSProperties}>
      {children}
    </div>
  )
}
