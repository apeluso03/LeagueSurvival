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
