import { memo, useEffect, useRef, type CSSProperties } from 'react'
import { splashUrl } from '../lib/champions'
import { CARD_PX, FINAL_INDEX, GAP_PX, QUART_FALLBACK, classColor, optionIndexes, quartEasing, reelPosition, tickSchedule } from '../lib/reel'
import { scheduleTicks } from '../lib/sound'
import type { Champion } from '../types'

const EASING =
  typeof CSS !== 'undefined' && CSS.supports?.('animation-timing-function', 'linear(0, 1)') ? quartEasing() : QUART_FALLBACK

type Props = {
  label: string
  strip: string[]
  championMap: Map<string, Champion>
  startAt: number
  durationMs: number
  offset: number
  master: boolean
  /** Plays the tick sounds (defaults to `master`). With staggered stops it's the last reel. */
  ticks?: boolean
  skipped: boolean
  onDone?: () => void
  /** Called when this reel lands (every reel, not just the master). */
  onLand?: () => void
  /** Draft-phase layout: a player slot (team colour) beside the reel that fills in on landing. */
  team?: string
  /** How many of the cards around the landing spot are this player's options (they stay lit). */
  optionCount?: number
}

/**
 * One case-opening reel (SPEC 17.3). Reels mounted together start together (on the first painted
 * frame); `startAt` only identifies a spin. A longer `durationMs` per reel makes them stop one after
 * another. Only the `master`
 * reel reports when the spin is over, and only one reel plays tick sounds.
 *
 * Performance: React renders the strip once, the motion is a compositor animation (Web Animations
 * API), and landing flips a data attribute so CSS dims the losers and lights up the winner. Nothing
 * re-renders or re-lays-out while the reels spin.
 */
function CaseReelImpl({ label, strip, championMap, startAt, durationMs, offset, master, ticks = master, skipped, onDone, onLand, team, optionCount = 1 }: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  const stripRef = useRef<HTMLDivElement>(null)
  const doneRef = useRef(onDone)
  const landRef = useRef(onLand)
  useEffect(() => {
    doneRef.current = onDone
    landRef.current = onLand
  }, [onDone, onLand])

  useEffect(() => {
    const el = stripRef.current
    if (!el) return
    const to = (t: number) => `translate3d(${(-reelPosition(t, offset)).toFixed(1)}px, 0, 0)`
    let finished = false
    const finish = () => {
      if (finished) return
      finished = true
      el.style.transform = to(1)
      rootRef.current?.setAttribute('data-landed', '')
      if (!skipped) landRef.current?.()
      if (master) doneRef.current?.()
    }
    if (skipped) {
      finish()
      return
    }

    // The compositor runs the motion; no JavaScript touches the strip while it spins.
    // No fixed start time: animations created in the same commit start together on the first frame
    // after the reels are painted, so mounting them (or a slow render) can never eat into the spin.
    el.style.transform = to(0)
    const anim = el.animate([{ transform: to(0) }, { transform: to(1) }], {
      duration: durationMs,
      easing: EASING,
      fill: 'forwards',
    })
    anim.onfinish = finish

    // Every tick is scheduled up front on the audio clock (one reel only), from the real start time.
    let silence = () => {}
    let cancelled = false
    if (ticks) {
      anim.ready
        .then(() => {
          const started = typeof anim.startTime === 'number' ? anim.startTime : performance.now()
          if (!cancelled) silence = scheduleTicks(tickSchedule(offset, durationMs), started)
        })
        .catch(() => {}) // cancelled before it started (Skip, or leaving the page)
    }
    return () => {
      cancelled = true
      silence()
      anim.onfinish = null
      anim.cancel()
    }
  }, [startAt, durationMs, offset, master, ticks, skipped])

  const winner = championMap.get(strip[FINAL_INDEX])
  const optionAt = new Map(optionIndexes(optionCount).map((idx, n) => [idx, n + 1]))
  const reelWindow = (
      <div className="reel-window" aria-label={`${label}'s reel`}>
        <div ref={stripRef} className="reel-strip" style={{ gap: GAP_PX }}>
          {strip.map((id, i) => {
            const champ = championMap.get(id)
            const n = optionAt.get(i)
            return (
              <div
                key={i}
                data-option={n && n > 1 ? n : undefined}
                className={i === FINAL_INDEX ? 'reel-card reel-card-winner' : n ? 'reel-card reel-card-option' : 'reel-card'}
                style={{ width: CARD_PX, ['--c' as string]: classColor(champ?.tags) }}
              >
                {champ?.image_url && <img src={champ.image_url} alt="" decoding="async" draggable={false} />}
                <span>{champ?.name}</span>
              </div>
            )
          })}
        </div>
        <div className="reel-fade reel-fade-left" />
        <div className="reel-fade reel-fade-right" />
        <div className="reel-marker" />
      </div>
  )

  if (team) {
    // The winner's splash is in the page from the start (hidden), so it has loaded by the time it shows.
    const art = winner ? splashUrl({ champion_id: winner.id, image_url: winner.image_url }) : null
    return (
      <div ref={rootRef} className="case-reel draft-row" style={{ '--team': team } as CSSProperties}>
        <div className="draft-slot">
          {art && <img className="draft-slot-art" src={art} alt="" decoding="async" draggable={false} />}
          <span className="draft-slot-shade" aria-hidden />
          <span className="lower-third relative text-sm">
            <span className="lt-name">{label}</span>
          </span>
          <div className="draft-slot-status relative">
            <span className="draft-picking">
              <span className="live-dot" /> Picking
            </span>
            <span className="draft-locked">
              <small>Locked in</small>
              <b className="reel-winner-name">{winner?.name}</b>
            </span>
          </div>
        </div>
        {reelWindow}
      </div>
    )
  }
  return (
    <div ref={rootRef} className="case-reel flex flex-col gap-1.5">
      <div className="flex items-center justify-between px-1">
        <span className="font-display text-sm font-bold text-gold-100">{label}</span>
        <span className="reel-winner-name text-xs font-semibold text-gold-300">{winner?.name}</span>
      </div>
      {reelWindow}
    </div>
  )
}

/** Re-renders of the Wheels page (e.g. background polling) never touch a spinning reel. */
export const CaseReel = memo(
  CaseReelImpl,
  (a, b) =>
    a.strip === b.strip &&
    a.startAt === b.startAt &&
    a.skipped === b.skipped &&
    a.offset === b.offset &&
    a.durationMs === b.durationMs &&
    a.championMap === b.championMap &&
    a.team === b.team &&
    a.optionCount === b.optionCount &&
    a.label === b.label,
)
