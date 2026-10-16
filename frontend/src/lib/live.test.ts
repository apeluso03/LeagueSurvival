import { describe, expect, it } from 'vitest'
import type { LivePlayer } from '../types'
import { clock, contractProgress, goldShort, pairLanes } from './live'

const p = (name: string, team: 100 | 200, position = ''): LivePlayer => ({
  name,
  champion_id: null,
  team,
  position,
  level: 1,
  kills: 3,
  deaths: 0,
  assists: 8,
  cs: 0,
  wards: 0,
  items: [],
  item_gold: 0,
  spells: [],
  keystone: null,
  dead: false,
  respawn: 0,
  player_id: null,
  option_index: null,
})

describe('live helpers', () => {
  it('formats the clock and gold', () => {
    expect(clock(754)).toBe('12:34')
    expect(clock(5)).toBe('0:05')
    expect(goldShort(12400)).toBe('12K')
    expect(goldShort(2450, true)).toBe('+2.5K')
    expect(goldShort(-800, true)).toBe('−800')
    expect(goldShort(0, true)).toBe('0')
  })

  it('pairs lanes by position, then by order', () => {
    const rows = pairLanes([p('a', 100, 'MIDDLE'), p('b', 100, 'TOP'), p('c', 200, 'TOP'), p('d', 200, 'MIDDLE'), p('e', 100), p('f', 200)])
    expect(rows.map((r) => [r.lane, r.blue?.name, r.red?.name])).toEqual([
      ['TOP', 'b', 'c'],
      ['MIDDLE', 'a', 'd'],
      ['', 'e', 'f'],
    ])
  })

  it('tracks contracts that can be seen live', () => {
    expect(contractProgress('kills', '10', p('a', 100))).toEqual({ now: 3, target: 10 })
    expect(contractProgress('assists', '15', p('a', 100))).toEqual({ now: 8, target: 15 })
    expect(contractProgress('rating', 'A', p('a', 100))).toBeNull()
  })
})
