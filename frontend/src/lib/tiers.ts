import type { AchievementInfo } from '../types'

/** Achievement tier colours (Trophies tab and the unlock popup). */
export const TIER_COLORS: Record<AchievementInfo['tier'], string> = {
  bronze: '#c98a4b',
  silver: '#c3ccd8',
  gold: '#e8c97a',
  prismatic: '#b98cff',
}
