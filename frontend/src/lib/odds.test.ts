import { describe, expect, it } from 'vitest'
import { mulberry32, nextMilestone, oddsTargets, shrunkWinRate, simulateRun } from './odds'

const base = { wins: 0, games: 0, alive: 160, total: 170, tokens: 0, streak: 0, players: 3, targets: [10] }
const chance = (o: ReturnType<typeof simulateRun>, t: number) => o.reach.find((r) => r.target === t)!.chance

describe('survival odds', () => {
  it('shrinks early win rates toward 50%', () => {
    expect(shrunkWinRate(0, 0)).toBe(0.5)
    expect(shrunkWinRate(2, 2)).toBeCloseTo(7 / 12)
    expect(shrunkWinRate(60, 100)).toBeCloseTo(65 / 110)
  })

  it('is certain when the target is already reached, and impossible with no champions', () => {
    expect(chance(simulateRun({ ...base, wins: 12, games: 20, targets: [10] }, 200), 10)).toBe(1)
    expect(chance(simulateRun({ ...base, alive: 2, targets: [1], games: 1000 }, 200), 1)).toBeLessThan(1)
    expect(simulateRun({ ...base, alive: 2, targets: [5] }, 200).medianWins).toBeLessThan(5)
  })

  it('better win rates go further', () => {
    const weak = simulateRun({ ...base, wins: 30, games: 100, targets: [50, 100] }, 500)
    const strong = simulateRun({ ...base, wins: 70, games: 100, targets: [50, 100] }, 500)
    expect(strong.medianWins).toBeGreaterThan(weak.medianWins)
    expect(chance(strong, 50)).toBeGreaterThan(chance(weak, 50))
    expect(chance(strong, 100)).toBeLessThanOrEqual(chance(strong, 50)) // further goals are never likelier
  })

  it('is repeatable with the same seed', () => {
    const a = simulateRun({ ...base, wins: 9, games: 12 }, 300, mulberry32(7))
    const b = simulateRun({ ...base, wins: 9, games: 12 }, 300, mulberry32(7))
    expect(a).toEqual(b)
  })

  it('finds the next milestone', () => {
    expect(nextMilestone(0)).toBe(10)
    expect(nextMilestone(9)).toBe(10)
    expect(nextMilestone(10)).toBe(20)
    expect(oddsTargets(11)).toEqual([20, 50, 100])
    expect(oddsTargets(45)).toEqual([50, 100, 200])
  })
})
