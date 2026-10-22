import { describe, expect, it } from 'vitest'
import type { Assignment, LiveGame } from '../types'
import { realRoles, rolesByChampion } from './roles'

const assignment = (player_id: number, played_role: Assignment['played_role'] = null): Assignment => ({
  player_id,
  options: [],
  played_champion_id: null,
  played_option_index: null,
  played_role,
})

const live = (roles: LiveGame['roles']) => ({ roles }) as LiveGame

describe('realRoles', () => {
  it('uses the live game, with roles set by hand on top', () => {
    const roles = realRoles(
      [assignment(1, 'TOP'), assignment(2)],
      live({ '1': { role: 'JUNGLE', source: 'smite' }, '2': { role: 'UTILITY', source: 'game' } }),
    )
    expect(roles.get(1)).toEqual({ role: 'TOP', source: 'set' })
    expect(roles.get(2)).toEqual({ role: 'UTILITY', source: 'game' })
  })

  it('drops a stale hand-set role once the assignments say it was cleared', () => {
    const stale = live({ '1': { role: 'TOP', source: 'set' } })
    expect(realRoles([assignment(1)], stale).has(1)).toBe(false)
    expect(realRoles(undefined, stale).get(1)).toEqual({ role: 'TOP', source: 'set' })
  })

  it('maps known roles onto champions for the build suggester', () => {
    const roles = realRoles(undefined, live({ '1': { role: 'JUNGLE', source: 'smite' } }))
    expect(
      rolesByChampion(
        [
          { playerId: 1, championId: 'Pantheon' },
          { playerId: 2, championId: 'Lux' },
        ],
        roles,
      ),
    ).toEqual({ Pantheon: 'JUNGLE' })
  })
})
