import { describe, expect, it } from 'vitest'
import { BUBBLE_PX, clampToPool, columns, hash, initialLayout, poolHeight, step } from './poolLayout'

describe('hash', () => {
  it('is stable and in [0, 1)', () => {
    expect(hash('Ahri')).toBe(hash('Ahri'))
    expect(hash('Ahri')).not.toBe(hash('Annie'))
    for (const s of ['a', 'MonkeyKing', 'Zyra']) {
      expect(hash(s)).toBeGreaterThanOrEqual(0)
      expect(hash(s)).toBeLessThan(1)
    }
  })
})

describe('initialLayout', () => {
  const ids = Array.from({ length: 40 }, (_, i) => `C${i}`)

  it('places every champion inside the pool without overlapping', () => {
    const width = 600
    const height = poolHeight(ids.length, width)
    const layout = initialLayout(ids, width)
    expect(layout.size).toBe(40)
    const pts = [...layout.values()]
    for (const p of pts) {
      expect(p.x).toBeGreaterThanOrEqual(0)
      expect(p.y).toBeGreaterThanOrEqual(0)
      expect(p.x + BUBBLE_PX).toBeLessThanOrEqual(width)
      expect(p.y + BUBBLE_PX).toBeLessThanOrEqual(height)
    }
    for (let i = 0; i < pts.length; i++)
      for (let j = i + 1; j < pts.length; j++)
        expect(Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y)).toBeGreaterThanOrEqual(BUBBLE_PX - 0.001)
  })

  it('is the same every time for the same champions', () => {
    expect([...initialLayout(ids, 500).entries()]).toEqual([...initialLayout(ids, 500).entries()])
  })

  it('grows taller on narrow screens', () => {
    expect(columns(360)).toBeLessThan(columns(1100))
    expect(poolHeight(170, 360)).toBeGreaterThan(poolHeight(170, 1100))
    expect(poolHeight(0, 800)).toBe(200)
  })
})

describe('step', () => {
  it('moves, slows down and eventually stops', () => {
    let s = { pos: { x: 100, y: 100 }, vel: { x: 1, y: 0 }, moving: true }
    let frames = 0
    while (s.moving && frames < 1000) {
      s = step(s.pos, s.vel, 16, 2000, 2000)
      frames++
    }
    expect(s.moving).toBe(false)
    expect(s.pos.x).toBeGreaterThan(100)
    expect(frames).toBeLessThan(200)
  })

  it('bounces off the walls and stays inside', () => {
    const s = step({ x: 290, y: 50 }, { x: 5, y: 0 }, 16, 300, 200)
    expect(s.vel.x).toBeLessThan(0)
    expect(s.pos.x + BUBBLE_PX).toBeLessThanOrEqual(300)
  })

  it('clamps dropped positions into the pool', () => {
    expect(clampToPool({ x: -50, y: 999 }, 300, 200)).toEqual({ x: 4, y: 200 - BUBBLE_PX - 4 })
  })
})
