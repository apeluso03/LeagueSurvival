import { describe, expect, it } from 'vitest'
import { allTags, filterChampions, splashUrl } from './champions'

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

describe('splashUrl', () => {
  it('builds the unversioned splash path from a portrait url', () => {
    const image_url = 'https://ddragon.leagueoflegends.com/cdn/16.19.1/img/champion/MonkeyKing.png'
    expect(splashUrl({ champion_id: 'MonkeyKing', image_url })).toBe(
      'https://ddragon.leagueoflegends.com/cdn/img/champion/splash/MonkeyKing_0.jpg',
    )
    expect(splashUrl({ champion_id: 'X', image_url: '' })).toBeNull()
  })
})
