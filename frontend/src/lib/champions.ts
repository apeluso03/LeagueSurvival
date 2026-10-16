export interface Searchable {
  name: string
  tags: string[]
}

/** Case-insensitive name search plus optional class tag filter. Ignores spaces and punctuation. */
export function filterChampions<T extends Searchable>(list: T[], search: string, tag?: string | null): T[] {
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '')
  const q = norm(search)
  return list.filter((c) => (!tag || c.tags.includes(tag)) && (!q || norm(c.name).includes(q)))
}

export function allTags(list: Searchable[]): string[] {
  return [...new Set(list.flatMap((c) => c.tags))].sort()
}

/** Splash art from Data Dragon (it lives outside the versioned path the portraits use). */
export function splashUrl(entry: { champion_id: string; image_url: string }): string | null {
  const m = entry.image_url.match(/^(.*)\/cdn\/[^/]+\/img\/champion\//)
  return m ? `${m[1]}/cdn/img/champion/splash/${entry.champion_id}_0.jpg` : null
}

/** Tall "loading screen" art from Data Dragon, which fits a portrait card. */
export function loadingUrl(entry: { champion_id: string; image_url: string }): string | null {
  const m = entry.image_url.match(/^(.*)\/cdn\/[^/]+\/img\/champion\//)
  return m ? `${m[1]}/cdn/img/champion/loading/${entry.champion_id}_0.jpg` : null
}

// --- Pool tab: quick filters and sorting --------------------------------------------------------

export interface Line {
  offered: number
  played: number
  wins: number
  on_spin: number[]
}

export interface PoolItem extends Searchable {
  champion_id: string
  shield_item_id: number | null
  eliminated_at: string | null
}

export type QuickFilter = 'shielded' | 'played' | 'never-played' | 'on-spin'
export type PoolSort = 'name' | 'most-played' | 'win-rate' | 'recent' | 'never-rolled'

export const QUICK_FILTERS: { id: QuickFilter; label: string }[] = [
  { id: 'shielded', label: 'Shielded' },
  { id: 'played', label: 'Played' },
  { id: 'never-played', label: 'Never played' },
  { id: 'on-spin', label: 'On the current spin' },
]

export const POOL_SORTS: { id: PoolSort; label: string }[] = [
  { id: 'name', label: 'A–Z' },
  { id: 'most-played', label: 'Most played' },
  { id: 'win-rate', label: 'Best win rate' },
  { id: 'recent', label: 'Recently eliminated' },
  { id: 'never-rolled', label: 'Never rolled first' },
]

const EMPTY: Line = { offered: 0, played: 0, wins: 0, on_spin: [] }

export function matchesQuick(e: PoolItem, line: Line | undefined, f: QuickFilter | null): boolean {
  const l = line ?? EMPTY
  switch (f) {
    case 'shielded':
      return e.shield_item_id != null
    case 'played':
      return l.played > 0
    case 'never-played':
      return l.played === 0
    case 'on-spin':
      return l.on_spin.length > 0
    default:
      return true
  }
}

/** Sorted copy. Ties (and "recent" for champions that are still alive) fall back to A–Z. */
export function sortPool<T extends PoolItem>(list: T[], lines: Record<string, Line>, sort: PoolSort): T[] {
  const l = (e: T) => lines[e.champion_id] ?? EMPTY
  const key: (e: T) => number = {
    name: () => 0,
    'most-played': (e: T) => -l(e).played,
    // Unplayed champions go last; among played ones, more games breaks a win-rate tie.
    'win-rate': (e: T) => (l(e).played ? -(l(e).wins / l(e).played) * 1000 - l(e).played : 1),
    recent: (e: T) => (e.eliminated_at ? -Date.parse(e.eliminated_at) : 0),
    'never-rolled': (e: T) => l(e).offered,
  }[sort]
  return [...list].sort((a, b) => key(a) - key(b) || a.name.localeCompare(b.name))
}
