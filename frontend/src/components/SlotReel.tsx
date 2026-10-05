import { useEffect, useMemo, useState } from 'react'
import { reelSequence } from '../lib/champions'
import type { Champion } from '../types'
import { ChampionPortrait } from './ui'

const ITEM_PX = 80 // matches the "lg" portrait (h-20)
const STRIP_LENGTH = 28

/**
 * A vertical slot-machine reel of portraits that scrolls and lands on `finalId`.
 * Portraits only, so it stays readable with 150+ champions (SPEC 10.1).
 */
export function SlotReel({
  pool,
  finalId,
  championMap,
  durationMs,
  onLanded,
}: {
  pool: string[]
  finalId: string
  championMap: Map<string, Champion>
  durationMs: number
  onLanded: () => void
}) {
  const strip = useMemo(() => reelSequence(pool, finalId, STRIP_LENGTH), [pool, finalId])
  const [started, setStarted] = useState(false)

  useEffect(() => {
    const raf = requestAnimationFrame(() => requestAnimationFrame(() => setStarted(true)))
    const timer = setTimeout(onLanded, durationMs)
    return () => {
      cancelAnimationFrame(raf)
      clearTimeout(timer)
    }
  }, [])

  return (
    <div
      className="relative overflow-hidden rounded-lg ring-2 ring-gold-500/70"
      style={{ height: ITEM_PX, width: ITEM_PX }}
      aria-label="Spinning"
    >
      <div
        style={{
          transform: `translateY(${started ? -(strip.length - 1) * ITEM_PX : 0}px)`,
          transition: `transform ${durationMs}ms cubic-bezier(0.12, 0.8, 0.2, 1)`,
        }}
      >
        {strip.map((id, i) => (
          <ChampionPortrait key={i} champion={championMap.get(id)} size="lg" className="rounded-none" />
        ))}
      </div>
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/40" />
    </div>
  )
}
