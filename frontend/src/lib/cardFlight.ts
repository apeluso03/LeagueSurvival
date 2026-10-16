/**
 * Revive animation for the Pool tab: the champion's card slides from where it sat in the
 * Eliminated grid to its new spot in the Alive grid, colouring in on the way, then glows.
 * One temporary element animated by the compositor; nothing else moves.
 */

export interface DocRect {
  x: number // page coordinates (scroll included), so a scroll before take-off doesn't matter
  y: number
  width: number
  height: number
}

export function docRect(el: Element): DocRect {
  const r = el.getBoundingClientRect()
  return { x: r.left + window.scrollX, y: r.top + window.scrollY, width: r.width, height: r.height }
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
const FLIGHT_MS = 720

function glow(el: HTMLElement) {
  el.classList.remove('revive-glow')
  void el.offsetWidth // restart the animation if it was already playing
  el.classList.add('revive-glow')
  el.addEventListener('animationend', () => el.classList.remove('revive-glow'), { once: true })
}

/** Wait for `[data-card-id=id]` inside `root`, bring it on screen, fly a copy of `imageUrl` in from `from`. */
export async function flyCardTo({
  root,
  id,
  imageUrl,
  from,
}: {
  root: HTMLElement
  id: string
  imageUrl: string | null
  from: DocRect | null
}) {
  const target = await waitFor(() => root.querySelector<HTMLElement>(`[data-card-id="${CSS.escape(id)}"]`), 2500)
  if (!target) return
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  let rect = target.getBoundingClientRect()
  if (rect.top < 90 || rect.bottom > window.innerHeight - 20) {
    target.scrollIntoView({ block: 'center', behavior: reduced ? 'auto' : 'smooth' })
    await sleep(reduced ? 0 : 450)
    rect = target.getBoundingClientRect()
  }
  if (reduced || !from || !imageUrl) return glow(target)

  const ghost = document.createElement('img')
  ghost.src = imageUrl
  ghost.alt = ''
  Object.assign(ghost.style, {
    position: 'fixed',
    top: '0',
    left: '0',
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    borderRadius: '14px',
    objectFit: 'cover',
    objectPosition: '50% 15%',
    transformOrigin: '0 0',
    zIndex: '70',
    pointerEvents: 'none',
    boxShadow: '0 0 0 2px #f0e6d2, 0 18px 40px -8px rgb(0 0 0 / 0.8), 0 0 28px rgb(46 155 255 / 0.55)',
    willChange: 'transform, filter',
  })
  document.body.appendChild(ghost)
  target.style.visibility = 'hidden'

  const sx = from.x - window.scrollX
  const sy = from.y - window.scrollY
  const scale = from.width / rect.width
  const midX = (sx + rect.left) / 2
  const midY = Math.min(sy, rect.top) - 40
  try {
    await ghost.animate(
      [
        { transform: `translate3d(${sx}px, ${sy}px, 0) scale(${scale})`, filter: 'grayscale(1) brightness(0.7)' },
        { transform: `translate3d(${midX}px, ${midY}px, 0) scale(1.1)`, filter: 'grayscale(0.4) brightness(1.1)', offset: 0.55 },
        { transform: `translate3d(${rect.left}px, ${rect.top}px, 0) scale(1)`, filter: 'grayscale(0) brightness(1)' },
      ],
      { duration: FLIGHT_MS, easing: 'cubic-bezier(0.35, 0.1, 0.25, 1)' },
    ).finished
  } catch {
    /* cancelled */
  }
  ghost.remove()
  target.style.visibility = ''
  glow(target)
}
