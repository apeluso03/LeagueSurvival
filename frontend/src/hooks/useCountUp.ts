import { useEffect, useRef, useState } from 'react'

/** Animates a number toward `target` (like the in-game gold counter). Respects reduced motion. */
export function useCountUp(target: number, ms = 450): number {
  const [shown, setShown] = useState(target)
  const from = useRef(target)
  useEffect(() => {
    const start = from.current
    if (start === target) return
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduced) {
      from.current = target
      setShown(target)
      return
    }
    const t0 = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min((now - t0) / ms, 1)
      const value = Math.round(start + (target - start) * (1 - (1 - t) ** 3))
      setShown(value)
      if (t < 1) raf = requestAnimationFrame(tick)
      else from.current = target
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      from.current = target
    }
  }, [target, ms])
  return shown
}
