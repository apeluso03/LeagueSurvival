import { memo, useEffect, useRef } from 'react'
import { CARD_PX, FINAL_INDEX, GAP_PX, QUART_FALLBACK, classColor, quartEasing, reelPosition, tickSchedule } from '../lib/reel'
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
  skipped: boolean
  onDone?: () => void
}

/**
 * One case-opening reel (SPEC 17.3). Every reel in a spin gets the same `startAt` and
 * `durationMs`, so they move on one clock and land together. Only the `master` reel plays tick
 * sounds and reports when the spin is over.
 *
 * Performance: React renders the strip once, the motion is a compositor animation (Web Animations
 * API), and landing flips a data attribute so CSS dims the losers and lights up the winner. Nothing
 * re-renders or re-lays-out while the reels spin.
 */
function CaseReelImpl({ label, strip, championMap, startAt, durationMs, offset, master, skipped, onDone }: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  const stripRef = useRef<HTMLDivElement>(null)
  const doneRef = useRef(onDone)
  useEffect(() => {
    doneRef.current = onDone
  }, [onDone])

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
      if (master) doneRef.current?.()
    }
    if (skipped) {
      finish()
      return
    }

    // The compositor runs the motion; no JavaScript touches the strip while it spins.
    el.style.transform = to(0)
    const anim = el.animate([{ transform: to(0) }, { transform: to(1) }], {
      duration: durationMs,
      easing: EASING,
      fill: 'forwards',
    })
    anim.startTime = startAt // same clock for every reel, so they stay in sync
    anim.onfinish = finish

    // Every tick is scheduled up front on the audio clock (master reel only).
    const silence = master ? scheduleTicks(tickSchedule(offset, durationMs), startAt) : () => {}
    return () => {
      silence()
      anim.onfinish = null
      anim.cancel()
    }
  }, [startAt, durationMs, offset, master, skipped])

  const winner = championMap.get(strip[FINAL_INDEX])
  return (
    <div ref={rootRef} className="case-reel flex flex-col gap-1.5">
      <div className="flex items-center justify-between px-1">
        <span className="font-display text-sm font-bold text-gold-100">{label}</span>
        <span className="reel-winner-name text-xs font-semibold text-gold-300">{winner?.name}</span>
      </div>
      <div className="reel-window" aria-label={`${label}'s reel`}>
        <div ref={stripRef} className="reel-strip" style={{ gap: GAP_PX }}>
          {strip.map((id, i) => {
            const champ = championMap.get(id)
            return (
              <div
                key={i}
                className={i === FINAL_INDEX ? 'reel-card reel-card-winner' : 'reel-card'}
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
    a.championMap === b.championMap &&
    a.label === b.label,
)
