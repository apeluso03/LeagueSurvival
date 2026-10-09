import { describe, expect, it } from 'vitest'
import { num, pct, sortRows } from './stats'

describe('formatting', () => {
  it('formats percentages and numbers, with a dash for missing values', () => {
    expect(pct(0.666)).toBe('67%')
    expect(pct(null)).toBe('—')
    expect(num(3.14159)).toBe('3.1')
    expect(num(2, 2)).toBe('2.00')
    expect(num(undefined)).toBe('—')
  })
})

describe('sortRows', () => {
  const rows = [
    { name: 'b', kda: 2 },
    { name: 'a', kda: null },
    { name: 'c', kda: 5 },
  ]
  it('sorts numbers both ways with missing values last', () => {
    expect(sortRows(rows, (r) => r.kda, true).map((r) => r.name)).toEqual(['c', 'b', 'a'])
    expect(sortRows(rows, (r) => r.kda, false).map((r) => r.name)).toEqual(['b', 'c', 'a'])
  })
  it('sorts strings', () => {
    expect(sortRows(rows, (r) => r.name, false).map((r) => r.name)).toEqual(['a', 'b', 'c'])
  })
})
