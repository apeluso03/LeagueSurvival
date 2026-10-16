/**
 * Survival odds (Wheels tab): plays the rest of the run out many times with the group's win rate.
 *
 * Each simulated game is won with probability p. A win adds one to the streak, and every third
 * win in a row gives each player a revive token, which brings one champion back. A loss
 * eliminates one champion per player and resets the streak. The run is over once there are fewer
 * champions than players.
 */
export interface OddsInput {
  wins: number
  games: number
  alive: number
  total: number
  tokens: number
  streak: number
  players: number
  targets: number[] // win counts to estimate the chance of reaching
}

export interface Odds {
  winRate: number // the p used (shrunk toward 50% while there are few games)
  reach: { target: number; chance: number }[] // chance of reaching each target, 0..1
  medianWins: number // median final win count
  p90Wins: number // a lucky-run win count (90th percentile)
}

/** Win rate with a prior of 5 wins in 10 games, so a 2-0 start isn't read as 100%. */
export const shrunkWinRate = (wins: number, games: number) => (wins + 5) / (games + 10)

/** Small seeded generator so results are steady between renders (and testable). */
export function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const MAX_GAMES = 400 // a run this long is effectively "forever"

export function simulateRun(input: OddsInput, runs = 2000, rng: () => number = mulberry32(1234)): Odds {
  const p = shrunkWinRate(input.wins, input.games)
  const players = Math.max(1, input.players)
  const finals: number[] = []
  for (let r = 0; r < runs; r++) {
    let { wins, alive, tokens, streak } = input
    let dead = input.total - input.alive
    for (let g = 0; g < MAX_GAMES && alive >= players; g++) {
      if (rng() < p) {
        wins++
        streak++
        if (streak % 3 === 0) tokens += players
      } else {
        const lost = Math.min(players, alive)
        alive -= lost
        dead += lost
        streak = 0
      }
      // Spend tokens right away to bring champions back.
      const revive = Math.min(tokens, dead)
      alive += revive
      dead -= revive
      tokens -= revive
    }
    finals.push(wins)
  }
  finals.sort((a, b) => a - b)
  return {
    winRate: p,
    reach: input.targets.map((target) => ({ target, chance: finals.filter((w) => w >= target).length / runs })),
    medianWins: finals[Math.floor(runs / 2)],
    p90Wins: finals[Math.floor(runs * 0.9)],
  }
}

/** The next "round" milestone above the current wins: 10, 20, 30, ... */
export const nextMilestone = (wins: number) => (Math.floor(wins / 10) + 1) * 10

/** Three goals to show odds for: the next 10, then the next 50 and the next 100 beyond it. */
export function oddsTargets(wins: number): number[] {
  const t1 = nextMilestone(wins)
  const t2 = (Math.floor(t1 / 50) + 1) * 50
  const t3 = (Math.floor(t2 / 100) + 1) * 100
  return [t1, t2, t3]
}
