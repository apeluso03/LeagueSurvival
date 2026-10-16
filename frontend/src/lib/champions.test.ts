import { describe, expect, it } from 'vitest'
import { allTags, filterChampions, loadingUrl, matchesQuick, sortPool, splashUrl, type PoolItem, type PoolSort, type QuickFilter } from './champions'

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

describe('loadingUrl', () => {
  it('builds the tall loading-screen art path', () => {
    const image_url = 'https://ddragon.leagueoflegends.com/cdn/16.19.1/img/champion/Ahri.png'
    expect(loadingUrl({ champion_id: 'Ahri', image_url })).toBe(
      'https://ddragon.leagueoflegends.com/cdn/img/champion/loading/Ahri_0.jpg',
    )
  })
})

describe('pool sorting and quick filters', () => {
  const e = (name: string, extra: Partial<PoolItem> = {}): PoolItem => ({
    name,
    tags: [],
    champion_id: name,
    shield_item_id: null,
    eliminated_at: null,
    ...extra,
  })
  const list = [e('Zed'), e('Ahri', { shield_item_id: 4 }), e('Lux', { eliminated_at: '2026-10-01T10:00:00Z' }), e('Annie', { eliminated_at: '2026-10-03T10:00:00Z' })]
  const lines = {
    Zed: { offered: 3, played: 2, wins: 1, on_spin: [] },
    Lux: { offered: 1, played: 1, wins: 1, on_spin: [2] },
    Annie: { offered: 2, played: 3, wins: 3, on_spin: [] },
  }
  const names = (s: PoolSort) => sortPool(list, lines, s).map((x) => x.name)

  it('sorts', () => {
    expect(names('name')).toEqual(['Ahri', 'Annie', 'Lux', 'Zed'])
    expect(names('most-played')).toEqual(['Annie', 'Zed', 'Lux', 'Ahri'])
    expect(names('win-rate')).toEqual(['Annie', 'Lux', 'Zed', 'Ahri'])
    expect(names('recent')).toEqual(['Annie', 'Lux', 'Ahri', 'Zed'])
    expect(names('never-rolled')).toEqual(['Ahri', 'Lux', 'Annie', 'Zed'])
  })

  it('filters', () => {
    const pick = (f: QuickFilter) => list.filter((x) => matchesQuick(x, lines[x.name as keyof typeof lines], f)).map((x) => x.name)
    expect(pick('shielded')).toEqual(['Ahri'])
    expect(pick('played')).toEqual(['Zed', 'Lux', 'Annie'])
    expect(pick('never-played')).toEqual(['Ahri'])
    expect(pick('on-spin')).toEqual(['Lux'])
  })
})
