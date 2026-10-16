import { describe, expect, it } from 'vitest'
import { factLine } from './facts'

const f = (o: Partial<Parameters<typeof factLine>[0] & object> = {}) => ({
  you_games: 0, you_wins: 0, riot_games: 0, riot_wins: 0, group_games: 0, group_wins: 0, ...o,
})

describe('factLine', () => {
  it('says when nobody has played it', () => {
    expect(factLine(f())).toBe('Nobody has played it yet')
    expect(factLine(undefined)).toBe('')
  })
  it('combines your record, Riot games and the group', () => {
    expect(factLine(f({ you_games: 2, you_wins: 2, riot_games: 12, riot_wins: 7, group_games: 5, group_wins: 4 }))).toBe(
      'You 2–0 · Riot 58% of 12 · Group 4–1',
    )
  })
  it('skips the group when it is only you', () => {
    expect(factLine(f({ you_games: 1, you_wins: 0, group_games: 1 }))).toBe('You 0–1')
    expect(factLine(f({ group_games: 3, group_wins: 1 }))).toBe('New for you · Group 1–2')
  })
})
