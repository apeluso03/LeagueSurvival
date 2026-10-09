import {
  memo,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type RefObject,
} from 'react'
import { createPortal } from 'react-dom'
import { splash } from '../lib/flight'
import { BUBBLE_PX, clampToPool, initialLayout, poolHeight, step, type Point } from '../lib/poolLayout'
import type { PoolEntry } from '../types'

const DRAG_START_PX = 5
const LONG_PRESS_MS = 260

type Drag = {
  entry: PoolEntry
  el: HTMLButtonElement
  pointerId: number
  grab: Point // pointer offset inside the bubble
  start: Point
  last: Point
  lastT: number
  vel: Point
  active: boolean
  longPressTimer?: number
}

type BubbleProps = {
  entry: PoolEntry
  x: number
  y: number
  grave: boolean
  hl: boolean | null
  onPointerDown: (ev: ReactPointerEvent<HTMLButtonElement>, e: PoolEntry) => void
  onPointerMove: (ev: ReactPointerEvent<HTMLButtonElement>) => void
  onPointerUp: (ev: ReactPointerEvent<HTMLButtonElement>, cancelled?: boolean) => void
  onOpen: (e: PoolEntry) => void
}

/** One champion. Memoized: typing in search or moving another bubble doesn't re-render it. */
const Bubble = memo(function Bubble({ entry: e, x, y, grave, hl, onPointerDown, onPointerMove, onPointerUp, onOpen }: BubbleProps) {
  return (
    <button
      type="button"
      title={e.name}
      aria-label={`${e.name}${grave ? ' (eliminated)' : ''}`}
      data-id={e.champion_id}
      onPointerDown={(ev) => onPointerDown(ev, e)}
      onPointerMove={onPointerMove}
      onPointerUp={(ev) => onPointerUp(ev)}
      onPointerCancel={(ev) => onPointerUp(ev, true)}
      onKeyDown={(ev) => (ev.key === 'Enter' || ev.key === ' ') && (ev.preventDefault(), onOpen(e))}
      className={`bubble absolute cursor-grab touch-pan-y select-none active:cursor-grabbing ${hl ? 'is-match' : ''}`}
      style={{
        left: x,
        top: y,
        width: BUBBLE_PX,
        height: BUBBLE_PX,
        opacity: hl === false ? 0.16 : 1,
        zIndex: hl ? 2 : 1,
        transition: 'opacity 150ms ease-out',
      }}
    >
      <img
        src={e.image_url}
        alt=""
        draggable={false}
        loading="lazy"
        decoding="async"
        className={`h-full w-full rounded-full object-cover ring-2 ${
          grave ? 'opacity-70 grayscale-[0.85] ring-slate-600/80' : 'ring-hex-100/50'
        } ${hl ? 'ring-gold-300' : ''}`}
      />
    </button>
  )
})

/**
 * A pool of champion portraits (SPEC 17.4). Bubbles can be dragged and flung around the
 * pool just for fun; a short tap opens the champion's card. Dropping a bubble outside this pool
 * calls `onDropOutside`, which decides what happens (e.g. reviving from the Graveyard).
 *
 * Performance: nothing animates at rest. Dragging, flinging and splashes touch the DOM directly, so
 * a drag causes no React renders until the bubble settles (then only that bubble re-renders).
 */
export function ChampionPool({
  entries,
  variant,
  poolRef,
  title,
  subtitle,
  highlight,
  onOpen,
  onDropOutside,
  empty,
  arrivals,
}: {
  entries: PoolEntry[]
  variant: 'water' | 'grave'
  poolRef: RefObject<HTMLDivElement | null>
  title: ReactNode
  subtitle?: ReactNode
  highlight: (e: PoolEntry) => boolean | null // null = no filter active
  onOpen: (e: PoolEntry) => void
  onDropOutside: (e: PoolEntry, client: Point) => boolean
  empty: ReactNode
  /** Where newly arrived champions should appear (e.g. a revive dropped at a spot). */
  arrivals?: Map<string, Point>
}) {
  const [width, setWidth] = useState(0)
  const [moved, setMoved] = useState<Map<string, Point>>(new Map()) // spots the user dragged things to
  const ghostEl = useRef<HTMLDivElement>(null)
  const ghostImg = useRef<HTMLImageElement>(null)
  const drag = useRef<Drag | null>(null)
  const grave = variant === 'grave'

  // Latest values for the stable pointer handlers below.
  const latest = useRef({ onOpen, onDropOutside, height: 0 })

  useLayoutEffect(() => {
    const el = poolRef.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.round(e.contentRect.width)))
    ro.observe(el)
    setWidth(el.clientWidth)
    return () => ro.disconnect()
  }, [poolRef])

  const ids = useMemo(() => entries.map((e) => e.champion_id), [entries])
  const w = width || 600
  const height = poolHeight(entries.length, w)
  const layout = useMemo(() => initialLayout(ids, w), [ids, w])
  useEffect(() => {
    latest.current = { onOpen, onDropOutside, height }
  })

  // While a touch drag is active, stop the page from scrolling under the finger.
  useEffect(() => {
    const el = poolRef.current
    if (!el) return
    const block = (ev: TouchEvent) => drag.current?.active && ev.preventDefault()
    el.addEventListener('touchmove', block, { passive: false })
    return () => el.removeEventListener('touchmove', block)
  }, [poolRef])

  const handlers = useMemo(() => {
    const moveGhost = (client: Point) => {
      const d = drag.current
      if (ghostEl.current && d) {
        ghostEl.current.style.transform = `translate3d(${client.x - d.grab.x}px, ${client.y - d.grab.y}px, 0) scale(1.12)`
      }
    }
    const activate = (client: Point) => {
      const d = drag.current
      if (!d || d.active) return
      d.active = true
      if (ghostImg.current) ghostImg.current.src = d.entry.image_url
      if (ghostEl.current) ghostEl.current.style.display = 'block'
      d.el.style.visibility = 'hidden'
      moveGhost(client)
      if (navigator.vibrate) navigator.vibrate(8)
    }
    const hideGhost = (d: Drag) => {
      if (ghostEl.current) ghostEl.current.style.display = 'none'
      d.el.style.visibility = ''
    }
    const ripple = (x: number, y: number) => poolRef.current && splash(poolRef.current, x, y)
    // Let a released bubble drift with its momentum (DOM only), then remember where it settled.
    const fling = (el: HTMLButtonElement, id: string, from: Point, vel: Point, poolWidth: number) => {
      const h = latest.current.height
      const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      let state = { pos: from, vel: reduced ? { x: 0, y: 0 } : vel, moving: !reduced }
      let last = performance.now()
      const apply = () => {
        el.style.left = `${state.pos.x}px`
        el.style.top = `${state.pos.y}px`
      }
      apply()
      const frame = (now: number) => {
        state = step(state.pos, state.vel, Math.min(32, now - last), poolWidth, h)
        last = now
        apply()
        if (state.moving) requestAnimationFrame(frame)
        else setMoved((m) => new Map(m).set(id, state.pos))
      }
      if (state.moving) requestAnimationFrame(frame)
      else setMoved((m) => new Map(m).set(id, state.pos))
    }

    return {
      open(e: PoolEntry) {
        latest.current.onOpen(e)
      },
      onPointerDown(ev: ReactPointerEvent<HTMLButtonElement>, entry: PoolEntry) {
        if (ev.button !== 0) return
        const el = ev.currentTarget
        const rect = el.getBoundingClientRect()
        el.setPointerCapture(ev.pointerId)
        const client = { x: ev.clientX, y: ev.clientY }
        drag.current = {
          entry,
          el,
          pointerId: ev.pointerId,
          grab: { x: client.x - rect.left, y: client.y - rect.top },
          start: client,
          last: client,
          lastT: performance.now(),
          vel: { x: 0, y: 0 },
          active: false,
        }
        if (ev.pointerType === 'touch') {
          drag.current.longPressTimer = window.setTimeout(() => activate(drag.current?.last ?? client), LONG_PRESS_MS)
        }
      },
      onPointerMove(ev: ReactPointerEvent<HTMLButtonElement>) {
        const d = drag.current
        if (!d || d.pointerId !== ev.pointerId) return
        const client = { x: ev.clientX, y: ev.clientY }
        const now = performance.now()
        const dt = Math.max(1, now - d.lastT)
        d.vel = { x: (client.x - d.last.x) / dt, y: (client.y - d.last.y) / dt }
        d.last = client
        d.lastT = now
        if (!d.active) {
          const dist = Math.hypot(client.x - d.start.x, client.y - d.start.y)
          if (ev.pointerType === 'touch') {
            if (dist > 8) clearTimeout(d.longPressTimer) // it's a scroll, not a drag
            return
          }
          if (dist <= DRAG_START_PX) return
          activate(client)
        }
        moveGhost(client)
      },
      onPointerUp(ev: ReactPointerEvent<HTMLButtonElement>, cancelled = false) {
        const d = drag.current
        if (!d || d.pointerId !== ev.pointerId) return
        clearTimeout(d.longPressTimer)
        drag.current = null
        if (!d.active) {
          if (!cancelled && Math.hypot(ev.clientX - d.start.x, ev.clientY - d.start.y) <= 8) latest.current.onOpen(d.entry)
          return
        }
        hideGhost(d)
        if (cancelled) return
        const client = { x: ev.clientX, y: ev.clientY }
        const rect = poolRef.current!.getBoundingClientRect()
        const inside = client.x >= rect.left && client.x <= rect.right && client.y >= rect.top && client.y <= rect.bottom
        if (!inside) {
          latest.current.onDropOutside(d.entry, client) // handled elsewhere, or it floats back
          return
        }
        const dropped = clampToPool(
          { x: client.x - d.grab.x - rect.left, y: client.y - d.grab.y - rect.top },
          rect.width,
          latest.current.height,
        )
        ripple(dropped.x + BUBBLE_PX / 2, dropped.y + BUBBLE_PX / 2)
        fling(d.el, d.entry.champion_id, dropped, d.vel, rect.width)
      },
    }
  }, [poolRef])

  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className={`text-lg font-bold ${grave ? 'text-slate-300' : 'text-hex-100'}`}>{title}</h2>
        {subtitle && <span className="text-xs text-slate-400">{subtitle}</span>}
      </div>
      <div
        ref={poolRef}
        className={`relative overflow-hidden rounded-[2rem] ${grave ? 'pool-grave' : 'pool-water'}`}
        style={{ height, contain: 'layout paint' }}
      >
        {entries.length === 0 && (
          <div className="absolute inset-0 grid place-items-center px-6 text-center text-sm text-slate-400">{empty}</div>
        )}
        {width > 0 &&
          entries.map((e) => {
            const id = e.champion_id
            const p = clampToPool(moved.get(id) ?? arrivals?.get(id) ?? layout.get(id)!, w, height)
            return (
              <Bubble
                key={id}
                entry={e}
                x={p.x}
                y={p.y}
                grave={grave}
                hl={highlight(e)}
                onPointerDown={handlers.onPointerDown}
                onPointerMove={handlers.onPointerMove}
                onPointerUp={handlers.onPointerUp}
                onOpen={handlers.open}
              />
            )
          })}
      </div>
      {createPortal(
        <div
          ref={ghostEl}
          className="pointer-events-none fixed top-0 left-0 z-[60]"
          style={{ display: 'none', width: BUBBLE_PX, height: BUBBLE_PX, willChange: 'transform' }}
        >
          <img
            ref={ghostImg}
            alt=""
            className="h-full w-full rounded-full object-cover shadow-[0_14px_30px_-6px_rgb(0_0_0/0.8)] ring-2 ring-gold-300"
          />
        </div>,
        document.body,
      )}
    </section>
  )
}
