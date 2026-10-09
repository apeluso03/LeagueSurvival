import { describe, expect, it } from 'vitest'
import { arcPoints } from './flight'

describe('arcPoints', () => {
  it('starts at the source, ends at the target, and rises above both', () => {
    const a = { x: 100, y: 800 }
    const b = { x: 600, y: 300 }
    const pts = arcPoints(a, b, 20)
    expect(pts).toHaveLength(21)
    expect(pts[0]).toEqual(a)
    expect(pts.at(-1)!.x).toBeCloseTo(b.x)
    expect(pts.at(-1)!.y).toBeCloseTo(b.y)
    expect(Math.min(...pts.map((p) => p.y))).toBeLessThan(b.y) // it goes up and over
  })
  it('still arcs when source and target are the same spot', () => {
    const p = { x: 200, y: 200 }
    const pts = arcPoints(p, p, 10)
    expect(Math.min(...pts.map((q) => q.y))).toBeLessThan(200)
  })
})
