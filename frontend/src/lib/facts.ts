import type { OptionFact } from '../types'

const rec = (w: number, g: number) => `${w}–${g - w}`

/** "You 2–0 · Riot 58% of 12 · Group 4–1", or "Nobody has played it yet" when there's nothing. */
export function factLine(f: OptionFact | undefined): string {
  if (!f) return ''
  const parts: string[] = []
  parts.push(f.you_games ? `You ${rec(f.you_wins, f.you_games)}` : 'New for you')
  if (f.riot_games) parts.push(`Riot ${Math.round((f.riot_wins / f.riot_games) * 100)}% of ${f.riot_games}`)
  if (f.group_games && f.group_games !== f.you_games) parts.push(`Group ${rec(f.group_wins, f.group_games)}`)
  if (!f.you_games && !f.riot_games && !f.group_games) return 'Nobody has played it yet'
  return parts.join(' · ')
}
