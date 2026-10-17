import { useEffect, useId, useMemo, useRef, useState, type PointerEvent } from 'react'
import { BLUE, RED, SIDE_COLOR, SIDE_NAME, clock, goldShort } from '../lib/live'
import type { TeamId } from '../types'

const H = 160
const PAD = { top: 10, right: 44, bottom: 20, left: 8 }

/**
 * Item-gold lead over the game: blue's lead above the zero line, red's below. One series with a
 * polarity, so the two sides take the team colours and the zero line is the neutral midpoint.
 * Hover (or arrow keys) shows the lead at that minute.
 */
export function GoldLeadChart({ points, ourTeam }: { points: { t: number; diff: number }[]; ourTeam: TeamId | null }) {
  const clipId = useId()
  const [hover, setHover] = useState<number | null>(null)
  // Drawn at the container's real width (not scaled), so the 10px labels stay 10px.
  const box = useRef<HTMLDivElement>(null)
  const [W, setW] = useState(320)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(() => setW(Math.max(200, Math.round(el.clientWidth))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const geo = useMemo(() => {
    const maxT = Math.max(60, ...points.map((p) => p.t))
    const maxAbs = Math.max(1000, ...points.map((p) => Math.abs(p.diff)))
    const step = maxAbs > 8000 ? 5000 : maxAbs > 3000 ? 2000 : 1000
    const top = Math.ceil(maxAbs / step) * step
    const x = (t: number) => PAD.left + (t / maxT) * (W - PAD.left - PAD.right)
    const y = (d: number) => PAD.top + ((top - d) / (2 * top)) * (H - PAD.top - PAD.bottom)
    return { maxT, top, step, x, y }
  }, [points, W])

  if (points.length < 2) {
    return (
      <div ref={box}>
        <p className="py-6 text-center text-xs text-slate-500">The gold graph starts after the first minute.</p>
      </div>
    )
  }
  const { x, y, top, step, maxT } = geo
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.diff).toFixed(1)}`).join('')
  const area = `${line}L${x(points.at(-1)!.t).toFixed(1)},${y(0)}L${x(points[0].t).toFixed(1)},${y(0)}Z`
  const ticks: number[] = []
  for (let v = -top; v <= top; v += step) ticks.push(v)
  const minutes: number[] = []
  const every = maxT > 1800 ? 600 : 300
  for (let t = every; t < maxT; t += every) minutes.push(t)
  const h = hover != null ? points[hover] : null

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const t = ((((e.clientX - box.left) / box.width) * W - PAD.left) / (W - PAD.left - PAD.right)) * maxT
    let best = 0
    for (let i = 1; i < points.length; i++) if (Math.abs(points[i].t - t) < Math.abs(points[best].t - t)) best = i
    setHover(best)
  }
  const leader = (d: number): TeamId | null => (d > 0 ? BLUE : d < 0 ? RED : null)
  const label = (side: TeamId) => `${SIDE_NAME[side]}${ourTeam === side ? ' (you)' : ''}`

  return (
    <div ref={box}>
      {/* legend: which side of the zero line is whose lead */}
      <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
        {[BLUE, RED].map((side) => (
          <span key={side} className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-3 rounded-full" style={{ background: SIDE_COLOR[side] }} />
            {label(side)} ahead ({side === BLUE ? 'above' : 'below'} the line)
          </span>
        ))}
      </div>
      <figure className="relative m-0">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width={W}
          height={H}
          className="block touch-none outline-none"
          role="img"
          aria-label={`Item gold lead over time. Now: ${leader(points.at(-1)!.diff) ? `${label(leader(points.at(-1)!.diff)!)} ahead by ${goldShort(Math.abs(points.at(-1)!.diff))}` : 'even'}.`}
          tabIndex={0}
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowLeft') setHover((i) => Math.max(0, (i ?? points.length) - 1))
            if (e.key === 'ArrowRight') setHover((i) => Math.min(points.length - 1, (i ?? -1) + 1))
          }}
          onBlur={() => setHover(null)}
        >
          <defs>
            <clipPath id={`${clipId}-up`}>
              <rect x="0" y="0" width={W} height={y(0)} />
            </clipPath>
            <clipPath id={`${clipId}-down`}>
              <rect x="0" y={y(0)} width={W} height={H} />
            </clipPath>
          </defs>
          {ticks.map((v) => (
            <g key={v}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(v)}
                y2={y(v)}
                stroke={v === 0 ? '#5b6475' : '#1c222d'}
                strokeWidth={1}
              />
              <text x={W - PAD.right + 6} y={y(v) + 3.5} fontSize="10" fill="#7d8799">
                {v === 0 ? '0' : goldShort(Math.abs(v))}
              </text>
            </g>
          ))}
          {minutes.map((t) => (
            <text key={t} x={x(t)} y={H - 5} fontSize="10" fill="#7d8799" textAnchor="middle">
              {Math.round(t / 60)}m
            </text>
          ))}
          {/* blue lead above zero, red lead below: the same path clipped twice */}
          <g clipPath={`url(#${clipId}-up)`}>
            <path d={area} fill={SIDE_COLOR[BLUE]} opacity={0.14} />
            <path
              d={line}
              fill="none"
              stroke={SIDE_COLOR[BLUE]}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </g>
          <g clipPath={`url(#${clipId}-down)`}>
            <path d={area} fill={SIDE_COLOR[RED]} opacity={0.14} />
            <path
              d={line}
              fill="none"
              stroke={SIDE_COLOR[RED]}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </g>
          {h && (
            <g pointerEvents="none">
              <line x1={x(h.t)} x2={x(h.t)} y1={PAD.top} y2={H - PAD.bottom} stroke="#a6b0c2" strokeWidth={1} />
              <circle
                cx={x(h.t)}
                cy={y(h.diff)}
                r={4.5}
                fill={SIDE_COLOR[leader(h.diff) ?? BLUE]}
                stroke="#0b0e14"
                strokeWidth={2}
              />
            </g>
          )}
        </svg>
        {h && (
          <div
            className="pointer-events-none absolute top-1 rounded-sm bg-[#0b0e14]/95 px-2 py-1 text-[11px] whitespace-nowrap ring-1 ring-white/15"
            style={{
              left: `${(x(h.t) / W) * 100}%`,
              transform: `translateX(${x(h.t) > W * 0.6 ? '-105%' : '8px'})`,
            }}
          >
            <b className="text-white tabular-nums">{goldShort(Math.abs(h.diff))}</b>{' '}
            <span className="text-slate-400">
              {leader(h.diff) ? (
                <>
                  <span
                    className="mr-1 inline-block h-0.5 w-2.5 align-middle"
                    style={{ background: SIDE_COLOR[leader(h.diff)!] }}
                  />
                  {label(leader(h.diff)!)} ahead
                </>
              ) : (
                'even'
              )}{' '}
              · {clock(h.t)}
            </span>
          </div>
        )}
        {/* table view for screen readers */}
        <div className="sr-only">
          <table>
            <caption>Item gold lead by game time (positive: blue ahead)</caption>
            <tbody>
              {points.map((p) => (
                <tr key={p.t}>
                  <td>{clock(p.t)}</td>
                  <td>{p.diff}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </figure>
    </div>
  )
}
