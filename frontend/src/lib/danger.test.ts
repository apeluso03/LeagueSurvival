import { describe, expect, it } from 'vitest'
import { dangerInfo } from './danger'

describe('dangerInfo', () => {
  it('counts losses before options shrink and before spins are blocked', () => {
    expect(dangerInfo(160, 3, 3)).toMatchObject({ full: 9, minimum: 3, lossesUntilShrink: 50, lossesUntilBlocked: 52, level: 'safe' })
    expect(dangerInfo(30, 3, 3)).toMatchObject({ lossesUntilShrink: 7, level: 'warning' })
    expect(dangerInfo(15, 3, 3)).toMatchObject({ lossesUntilShrink: 2, level: 'danger' })
  })

  it('handles a pool already below full options', () => {
    expect(dangerInfo(7, 3, 3)).toMatchObject({ lossesUntilShrink: -1, lossesUntilBlocked: 1, level: 'danger' })
    expect(dangerInfo(2, 3, 3)).toMatchObject({ lossesUntilBlocked: -1 })
  })
})
