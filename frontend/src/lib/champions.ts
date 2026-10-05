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

/**
 * The strip of champion ids a slot reel scrolls through before it lands.
 * Random fillers, never the same id twice in a row, always ending on `finalId`.
 */
export function reelSequence(pool: string[], finalId: string, length: number, rng: () => number = Math.random): string[] {
  const seq: string[] = []
  const fillers = pool.length > 1 ? pool : [finalId]
  for (let i = 0; i < length - 1; i++) {
    let pick = fillers[Math.floor(rng() * fillers.length)]
    if (fillers.length > 1) {
      while (pick === seq[i - 1] || (i === length - 2 && pick === finalId)) {
        pick = fillers[Math.floor(rng() * fillers.length)]
      }
    }
    seq.push(pick)
  }
  seq.push(finalId)
  return seq
}
