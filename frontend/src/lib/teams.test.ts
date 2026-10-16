import { afterEach, describe, expect, it } from 'vitest'
import { TEAM_COLORS, defaultTeamColor, registerTeamColors, teamColor } from './teams'

describe('teamColor', () => {
  afterEach(() => registerTeamColors([]))

  it('gives the first eight players different colours and wraps after that', () => {
    expect(new Set([1, 2, 3, 4, 5, 6, 7, 8].map(teamColor)).size).toBe(8)
    expect(teamColor(9)).toBe(teamColor(1))
    expect(TEAM_COLORS).toContain(teamColor(0))
  })

  it('uses a colour the player picked', () => {
    registerTeamColors([{ id: 2, color: '#123456' }, { id: 3, color: null }])
    expect(teamColor(2)).toBe('#123456')
    expect(teamColor(3)).toBe(defaultTeamColor(3))
  })
})
