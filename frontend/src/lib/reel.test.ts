import { describe, expect, it } from 'vitest'
import {
  CARD_PX,
  FINAL_INDEX,
  STRIDE_PX,
  buildStrip,
  cardIndexAt,
  easeOutQuart,
  randomLandingOffset,
  reelPosition,
} from './reel'

describe('easeOutQuart', () => {
  it('starts at 0, ends at 1, clamps outside', () => {
    expect(easeOutQuart(0)).toBe(0)
    expect(easeOutQuart(1)).toBe(1)
    expect(easeOutQuart(-1)).toBe(0)
    expect(easeOutQuart(2)).toBe(1)
  })
  it('covers most of the distance early (slow, suspenseful finish)', () => {
    expect(easeOutQuart(0.5)).toBeGreaterThan(0.9)
  })
})

describe('reelPosition', () => {
  it('starts on the first card and lands inside the final card', () => {
    expect(cardIndexAt(reelPosition(0, 0))).toBe(0)
    for (const offset of [-40, 0, 40]) {
      const end = reelPosition(1, offset)
      expect(cardIndexAt(end)).toBe(FINAL_INDEX)
      expect(end).toBeCloseTo(FINAL_INDEX * STRIDE_PX + CARD_PX / 2 + offset)
    }
  })
  it('only moves forward', () => {
    let prev = -Infinity
    for (let t = 0; t <= 1; t += 0.01) {
      const p = reelPosition(t, 12)
      expect(p).toBeGreaterThanOrEqual(prev)
      prev = p
    }
  })
  it('two reels with the same clock land at the same time', () => {
    // Synced spins share t; whatever the offsets, both are on their final card at t = 1
    expect(cardIndexAt(reelPosition(1, -30))).toBe(cardIndexAt(reelPosition(1, 30)))
  })
})

describe('randomLandingOffset', () => {
  it('stays well inside the card', () => {
    for (const r of [0, 0.25, 0.5, 0.75, 0.999]) {
      expect(Math.abs(randomLandingOffset(() => r))).toBeLessThan(CARD_PX / 2 - 10)
    }
  })
})

describe('buildStrip', () => {
  const pool = ['A', 'B', 'C', 'D', 'E']
  it('puts the winner at the final index', () => {
    const strip = buildStrip(pool, 'C')
    expect(strip).toHaveLength(50)
    expect(strip[FINAL_INDEX]).toBe('C')
  })
  it('avoids back-to-back repeats and copies of the winner right next to it', () => {
    for (let i = 0; i < 30; i++) {
      const strip = buildStrip(pool, 'C')
      strip.slice(1).forEach((id, j) => expect(id).not.toBe(strip[j]))
      expect(strip[FINAL_INDEX - 1]).not.toBe('C')
      expect(strip[FINAL_INDEX + 1]).not.toBe('C')
    }
  })
  it('works with a tiny pool', () => {
    expect(buildStrip(['Z'], 'Z', 5, 3)).toEqual(['Z', 'Z', 'Z', 'Z', 'Z'])
  })
})

describe('quartEasing', () => {
  it('is a CSS linear() curve from 0 to 1 that follows easeOutQuart', async () => {
    const { quartEasing } = await import('./reel')
    const css = quartEasing(4)
    expect(css).toBe('linear(0.0000 0.00%, 0.6836 25.00%, 0.9375 50.00%, 0.9961 75.00%, 1.0000 100.00%)')
  })
})

describe('tickSchedule', () => {
  it('has one tick per card crossing, in order, matching the reel position', async () => {
    const { tickSchedule, reelPosition: pos, cardIndexAt: idx } = await import('./reel')
    const ticks = tickSchedule(10, 6500)
    expect(ticks.length).toBe(FINAL_INDEX)
    for (let i = 1; i < ticks.length; i++) expect(ticks[i][0]).toBeGreaterThan(ticks[i - 1][0])
    for (const [ms, t] of ticks) {
      expect(ms).toBeCloseTo(t * 6500)
      // just after each scheduled time, the marker is on the next card
      expect(idx(pos(t + 1e-6, 10))).toBe(idx(pos(t - 1e-6, 10)) + 1)
    }
  })
})
