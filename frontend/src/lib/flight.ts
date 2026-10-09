/**
 * Revive flight (SPEC 17.4): a revived champion arcs out of the Graveyard and splashes into the
 * Pool. One temporary element animated by the compositor; nothing else moves.
 */
import { BUBBLE_PX, type Point } from './poolLayout'

/** A splash ring at (x, y) inside a pool element. Removes itself when done. */
export function splash(pool: HTMLElement, x: number, y: number, big = false) {
  const r = document.createElement('span')
  r.className = big ? 'ripple ripple-big' : 'ripple'
  r.style.left = `${x}px`
  r.style.top = `${y}px`
  r.addEventListener('animationend', () => r.remove())
  pool.appendChild(r)
  setTimeout(() => r.remove(), 1500) // in case animations are off
}

const FLIGHT_MS = 800
const SAMPLES = 24

/** Points along a curved arc from `a` to `b` that rises above both. */
export function arcPoints(a: Point, b: Point, samples = SAMPLES): Point[] {
  const dist = Math.hypot(b.x - a.x, b.y - a.y)
  const control = { x: (a.x + b.x) / 2, y: Math.min(a.y, b.y) - Math.max(90, dist * 0.35) }
  return Array.from({ length: samples + 1 }, (_, i) => {
    const t = i / samples
    const u = 1 - t
    return {
      x: u * u * a.x + 2 * u * t * control.x + t * t * b.x,
      y: u * u * a.y + 2 * u * t * control.y + t * t * b.y,
    }
  })
}

async function waitFor<T>(find: () => T | null | undefined, timeoutMs: number): Promise<T | null> {
  const until = performance.now() + timeoutMs
  while (performance.now() < until) {
    const found = find()
    if (found) return found
    await new Promise((r) => requestAnimationFrame(r))
  }
  return null
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/**
 * Fly `imageUrl` from `fromDoc` (page coordinates) to the champion's bubble in `pool` once it
 * appears there, then splash. `onSplash` gets the landing point in pool coordinates.
 */
export async function flyIntoPool({
  pool,
  id,
  imageUrl,
  fromDoc,
  onSplash,
}: {
  pool: HTMLElement
  id: string
  imageUrl: string
  fromDoc: Point
  onSplash: (x: number, y: number) => void
}) {
  const target = await waitFor(() => pool.querySelector<HTMLElement>(`[data-id="${CSS.escape(id)}"]`), 2500)
  if (!target) return
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  target.style.visibility = 'hidden'

  // Make sure the landing spot is on screen.
  let rect = target.getBoundingClientRect()
  if (rect.top < 90 || rect.bottom > window.innerHeight - 20) {
    target.scrollIntoView({ block: 'center', behavior: reduced ? 'auto' : 'smooth' })
    await sleep(reduced ? 0 : 450)
    rect = target.getBoundingClientRect()
  }
  const to = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
  const poolRect = pool.getBoundingClientRect()
  const land = () => {
    target.style.visibility = ''
    onSplash(to.x - poolRect.left, to.y - poolRect.top)
  }
  if (reduced) return land()

  const from = { x: fromDoc.x - window.scrollX, y: fromDoc.y - window.scrollY }
  const ghost = document.createElement('img')
  ghost.src = imageUrl
  ghost.alt = ''
  Object.assign(ghost.style, {
    position: 'fixed',
    top: '0',
    left: '0',
    width: `${BUBBLE_PX}px`,
    height: `${BUBBLE_PX}px`,
    borderRadius: '9999px',
    objectFit: 'cover',
    zIndex: '70',
    pointerEvents: 'none',
    boxShadow: '0 0 0 2px #f0e6d2, 0 14px 30px -6px rgb(0 0 0 / 0.8), 0 0 24px rgb(10 200 185 / 0.55)',
    willChange: 'transform, filter',
  })
  document.body.appendChild(ghost)

  const pts = arcPoints(from, to)
  const half = BUBBLE_PX / 2
  const frames = pts.map((p, i) => {
    const t = i / (pts.length - 1)
    const scale = 1 + 0.45 * Math.sin(Math.PI * t)
    return {
      transform: `translate3d(${p.x - half}px, ${p.y - half}px, 0) scale(${scale.toFixed(3)}) rotate(${(-360 * t).toFixed(1)}deg)`,
      filter: `grayscale(${(1 - t).toFixed(2)})`,
    }
  })
  try {
    await ghost.animate(frames, { duration: FLIGHT_MS, easing: 'cubic-bezier(0.35, 0.1, 0.25, 1)' }).finished
  } catch {
    /* cancelled */
  }
  ghost.remove()
  land()
  target.animate(
    [{ transform: 'scale(0.55)' }, { transform: 'scale(1.18)', offset: 0.55 }, { transform: 'scale(1)' }],
    { duration: 380, easing: 'ease-out' },
  )
}
