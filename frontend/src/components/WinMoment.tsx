import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { usePlayerMap } from '../hooks/queries'
import { playMilestone, playVictory } from '../lib/sound'
import type { Game } from '../types'
import { BroadcastBanner, ReplayChrome } from './ReplayChrome'

/** Streaks that get a banner: 5, 10, then every 10. */
export const isMilestone = (streak: number) => streak === 5 || (streak >= 10 && streak % 10 === 0)

const BASE_MS = 2400
const MILESTONE_MS = 3400
const TOKEN_FLY_AT_MS = 1500

/** Fly the token banner up to the header's token counter, then pulse the counter. */
function flyToCounter(el: HTMLElement) {
  const target = document.querySelector<HTMLElement>('[data-token-counter]')
  if (!target || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
  const from = el.getBoundingClientRect()
  const to = target.getBoundingClientRect()
  const dx = to.left + to.width / 2 - (from.left + from.width / 2)
  const dy = to.top + to.height / 2 - (from.top + from.height / 2)
  el.animate(
    [
      { transform: 'translate(0, 0) scale(1)', opacity: 1 },
      { transform: `translate(${dx * 0.5}px, ${dy * 0.5 - 40}px) scale(0.7)`, opacity: 1, offset: 0.5 },
      { transform: `translate(${dx}px, ${dy}px) scale(0.2)`, opacity: 0.2 },
    ],
    { duration: 650, easing: 'cubic-bezier(0.5, 0, 0.75, 0)', fill: 'forwards' },
  ).onfinish = () => {
    target.classList.remove('counter-pop')
    void target.offsetWidth
    target.classList.add('counter-pop')
  }
}

/**
 * A win: VICTORY with a gold burst, the streak counter ticking up, a banner on streak milestones,
 * and any revive tokens flying up to the header. Click or Esc skips it.
 */
export function WinMoment({ game, streak, onDone }: { game: Game; streak: number; onDone: () => void }) {
  const players = usePlayerMap()
  const milestone = isMilestone(streak)
  const [shown, setShown] = useState(Math.max(0, streak - 1))
  const tokenRef = useRef<HTMLDivElement>(null)
  const tokenNames = game.tokens_earned.map((p) => players.get(p)?.display_name ?? `Player ${p}`)

  useEffect(() => {
    playVictory()
    if (milestone) playMilestone()
    const tick = setTimeout(() => setShown(streak), 650)
    const fly = setTimeout(() => tokenRef.current && flyToCounter(tokenRef.current), TOKEN_FLY_AT_MS)
    const end = setTimeout(onDone, milestone ? MILESTONE_MS : BASE_MS)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onDone()
    window.addEventListener('keydown', onKey)
    return () => {
      ;[tick, fly, end].forEach(clearTimeout)
      window.removeEventListener('keydown', onKey)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game.id])

  return createPortal(
    <div
      className="win-overlay fixed inset-0 z-[80] flex flex-col items-center justify-center gap-4 overflow-hidden bg-black/60 p-4"
      style={{ ['--win-total' as string]: `${milestone ? MILESTONE_MS : BASE_MS}ms` }}
      onClick={onDone}
      role="dialog"
      aria-label={`Victory. Streak ${streak}`}
    >
      <div className="win-burst" aria-hidden />
      <ReplayChrome tag={`Replay · Game ${game.id}`} />
      <BroadcastBanner color="var(--color-hex-400)">
        <h2 className="win-title font-display relative text-5xl tracking-[0.2em] text-white uppercase sm:text-7xl">Victory</h2>
      </BroadcastBanner>
      <div className="streak-bar relative flex items-center gap-2 text-2xl font-bold text-gold-100 sm:text-3xl">
        <span className="win-flame" aria-hidden>
          🔥
        </span>
        <span key={shown} className="streak-flip tabular-nums">
          {shown}
        </span>
        <span className="text-base font-medium text-slate-300">in a row</span>
      </div>
      {milestone && (
        <div className="milestone-ribbon relative rounded-full px-6 py-2 font-display text-lg font-bold tracking-[0.2em] uppercase sm:text-2xl">
          {streak} win streak!
        </div>
      )}
      {tokenNames.length > 0 && (
        <div ref={tokenRef} className="token-banner relative rounded-2xl bg-gold-800/80 px-4 py-2 text-sm text-gold-100 ring-1 ring-gold-400/60">
          ✦ Revive token earned · {tokenNames.join(', ')}
        </div>
      )}
    </div>,
    document.body,
  )
}
