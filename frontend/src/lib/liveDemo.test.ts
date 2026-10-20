import { describe, expect, it } from 'vitest'
import type { Champion } from '../types'
import { makeDemoLive } from './liveDemo'

const champs: Champion[] = Array.from({ length: 20 }, (_, i) => ({
  id: `Champ${i}`,
  key: 1000 + i,
  name: `Champ ${i}`,
  title: '',
  tags: [],
  image_url: `https://ddragon.example/cdn/16.20.1/img/champion/Champ${i}.png`,
  ddragon_version: '16.20.1',
  positions: [],
}))

describe('live preview', () => {
  const ours = [
    { playerId: 1, championId: 'Champ3' },
    { playerId: 2, championId: 'Champ7' },
  ]

  it('builds a full 5v5 game with our players on blue', () => {
    const live = makeDemoLive({ ours, champions: champs, t: 900 })
    const st = live.state!
    expect(st.players).toHaveLength(10)
    expect(st.players.filter((p) => p.player_id != null).map((p) => p.champion_id)).toEqual(['Champ3', 'Champ7'])
    expect(new Set(st.players.map((p) => p.champion_id)).size).toBe(10) // nobody twice
    expect(st.our_team).toBe(100)
    expect(st.players[0].items[0].image).toBe('https://ddragon.example/cdn/16.20.1/img/item/6631.png')
    expect(st.teams['100'].kills).toBe(st.players.filter((p) => p.team === 100).reduce((n, p) => n + p.kills, 0))
    expect(st.gold_history.at(-1)!.diff).toBe(st.teams['100'].gold - st.teams['200'].gold) // graph ends at the bug's lead
  })

  it('moves with the clock and stays the same for the same players', () => {
    const early = makeDemoLive({ ours, champions: champs, t: 300 }).state!
    const late = makeDemoLive({ ours, champions: champs, t: 1600 }).state!
    expect(late.gold_history.length).toBeGreaterThan(early.gold_history.length)
    expect(late.events.length).toBeGreaterThan(early.events.length)
    const again = makeDemoLive({ ours, champions: champs, t: 300 }).state!
    expect(again.players.map((p) => p.champion_id)).toEqual(early.players.map((p) => p.champion_id))
  })
})
