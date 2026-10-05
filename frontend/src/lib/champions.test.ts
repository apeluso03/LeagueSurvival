import { describe, expect, it } from 'vitest'
import { allTags, filterChampions, reelSequence } from './champions'

const champs = [
  { name: "Kai'Sa", tags: ['Marksman'] },
  { name: 'Wukong', tags: ['Fighter', 'Tank'] },
  { name: 'Dr. Mundo', tags: ['Tank', 'Fighter'] },
  { name: 'Ahri', tags: ['Mage', 'Assassin'] },
]

describe('filterChampions', () => {
  it('matches names ignoring case and punctuation', () => {
    expect(filterChampions(champs, 'kais').map((c) => c.name)).toEqual(["Kai'Sa"])
    expect(filterChampions(champs, 'dr mun').map((c) => c.name)).toEqual(['Dr. Mundo'])
  })

  it('filters by tag', () => {
    expect(filterChampions(champs, '', 'Tank').map((c) => c.name)).toEqual(['Wukong', 'Dr. Mundo'])
    expect(filterChampions(champs, 'wu', 'Mage')).toEqual([])
  })

  it('returns everything for an empty query', () => {
    expect(filterChampions(champs, '')).toHaveLength(4)
  })
})

describe('allTags', () => {
  it('returns sorted unique tags', () => {
    expect(allTags(champs)).toEqual(['Assassin', 'Fighter', 'Mage', 'Marksman', 'Tank'])
  })
})

describe('reelSequence', () => {
  const pool = ['A', 'B', 'C', 'D']

  it('ends on the final id and has the requested length', () => {
    const seq = reelSequence(pool, 'C', 20)
    expect(seq).toHaveLength(20)
    expect(seq.at(-1)).toBe('C')
  })

  it('never repeats the same id twice in a row', () => {
    for (let i = 0; i < 50; i++) {
      const seq = reelSequence(pool, 'A', 30)
      seq.slice(1).forEach((id, j) => expect(id).not.toBe(seq[j]))
    }
  })

  it('works with a single-champion pool', () => {
    expect(reelSequence(['Z'], 'Z', 5)).toEqual(['Z', 'Z', 'Z', 'Z', 'Z'])
  })
})
