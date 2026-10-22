import type { Champion, LiveEvent, LiveGame, LiveItem, LivePlayer, LiveState, Role, TeamId } from '../types'
import { LANES } from './live'

/**
 * A made-up live game for previewing the Live tab without being in one (`/live?preview=1`).
 * Built entirely in the browser: nothing is saved and nothing calls Riot. Deterministic for a
 * given set of players and champions, and it moves with `t` (game seconds) so the clock, gold
 * graph and play-by-play change while you watch.
 */

// Finished items and boots by lane, so item rows look like real builds at different stages.
const ITEMS: Record<string, number[]> = {
  TOP: [6631, 3047, 3053, 3065, 3075, 3742],
  JUNGLE: [6676, 3111, 3071, 3036, 6694, 3026],
  MIDDLE: [6655, 3020, 3157, 3089, 3135, 3102],
  BOTTOM: [3031, 3006, 3094, 3036, 3072, 3046],
  UTILITY: [3190, 3117, 3107, 3222, 3504, 2065],
}
const TRINKET: Record<string, number> = { TOP: 3364, JUNGLE: 3364, MIDDLE: 3340, BOTTOM: 3340, UTILITY: 3364 }
const SPELL_TWO: Record<string, [string, string]> = {
  TOP: ['SummonerTeleport', 'Teleport'],
  JUNGLE: ['SummonerSmite', 'Smite'],
  MIDDLE: ['SummonerDot', 'Ignite'],
  BOTTOM: ['SummonerHeal', 'Heal'],
  UTILITY: ['SummonerExhaust', 'Exhaust'],
}
const KEYSTONE: Record<string, { id: number; name: string; path: string }> = {
  TOP: { id: 8010, name: 'Conqueror', path: 'perk-images/Styles/Precision/Conqueror/Conqueror.png' },
  JUNGLE: { id: 8128, name: 'Dark Harvest', path: 'perk-images/Styles/Domination/DarkHarvest/DarkHarvest.png' },
  MIDDLE: { id: 8112, name: 'Electrocute', path: 'perk-images/Styles/Domination/Electrocute/Electrocute.png' },
  BOTTOM: { id: 8008, name: 'Lethal Tempo', path: 'perk-images/Styles/Precision/LethalTempo/LethalTempoTemp.png' },
  UTILITY: { id: 8439, name: 'Aftershock', path: 'perk-images/Styles/Resolve/VeteranAftershock/VeteranAftershock.png' },
}
const DRAGONS = ['Fire', 'Water', 'Earth', 'Air', 'Hextech', 'Chemtech']
const ITEM_COST = 2900 // rough value of a finished item, for the gold estimate

/** Data Dragon base URL and version, taken from a champion's portrait URL. */
function ddragon(champions: Champion[]): { base: string; version: string } {
  const c = champions.find((x) => x.image_url)
  const m = c?.image_url.match(/^(https?:\/\/[^/]+)\/cdn\/([^/]+)\//)
  return m ? { base: m[1], version: m[2] } : { base: 'https://ddragon.leagueoflegends.com', version: c?.ddragon_version ?? '' }
}

/** Small seeded random numbers, so a preview looks the same each time for the same players. */
function seeded(seed: number) {
  let s = seed >>> 0 || 1
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 2 ** 32
  }
}

function hash(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619)
  return h >>> 0
}

export interface DemoPlayer {
  playerId: number
  championId: string
}

export function makeDemoLive(opts: { ours: DemoPlayer[]; champions: Champion[]; t: number; gameId?: number }): LiveGame {
  const { champions } = opts
  const t = Math.max(60, Math.round(opts.t))
  const { base, version } = ddragon(champions)
  const ours = opts.ours.slice(0, 5)
  const rand = seeded(hash(ours.map((o) => o.championId).join(',')))
  const taken = new Set(ours.map((o) => o.championId))
  const pool = champions.filter((c) => !taken.has(c.id))
  const pickOpponent = () => {
    const c = pool.splice(Math.floor(rand() * pool.length), 1)[0]
    return c?.id ?? null
  }

  const minutes = t / 60
  const lead = 1 + 0.25 * Math.sin(t / 300) // blue slowly ahead, with swings

  const item = (id: number, slot: number): LiveItem => ({
    id,
    name: null,
    image: version ? `${base}/cdn/${version}/img/item/${id}.png` : null,
    count: 1,
    slot,
  })
  const spell = (key: string, name: string) => ({ name, icon: version ? `${base}/cdn/${version}/img/spell/${key}.png` : null })

  const player = (team: TeamId, lane: string, championId: string | null, playerId: number | null): LivePlayer => {
    const strength = team === 100 ? lead : 2 - lead
    const owned = Math.min(6, Math.floor(minutes / 6.5 * strength + rand() * 0.8))
    const cs = Math.round(minutes * (lane === 'UTILITY' ? 1.2 : lane === 'JUNGLE' ? 5.5 : 7.4) * (0.9 + rand() * 0.2))
    const kills = Math.round((minutes / 4) * strength * (lane === 'UTILITY' ? 0.3 : 1) * (0.6 + rand() * 0.8))
    const dead = rand() < 0.12
    const items = ITEMS[lane].slice(0, owned).map(item)
    items.push(item(TRINKET[lane], 6))
    return {
      champion_id: championId,
      team,
      position: lane,
      level: Math.min(18, 1 + Math.floor(minutes / 1.6)),
      kills,
      deaths: Math.round((minutes / 5) * (2 - strength) * (0.5 + rand())),
      assists: Math.round((minutes / 2.5) * strength * (0.5 + rand())),
      cs,
      wards: Math.round(minutes * (lane === 'UTILITY' ? 2.2 : 0.7) * 10) / 10,
      items,
      item_gold: owned * ITEM_COST,
      spells: [spell('SummonerFlash', 'Flash'), spell(...SPELL_TWO[lane])],
      keystone: {
        id: KEYSTONE[lane].id,
        name: KEYSTONE[lane].name,
        icon: version ? `${base}/cdn/img/${KEYSTONE[lane].path}` : null,
      },
      dead,
      respawn: dead ? Math.round(6 + minutes * 0.9) : 0,
      player_id: playerId,
      option_index: playerId != null ? 0 : null,
    }
  }

  const players: LivePlayer[] = []
  LANES.forEach((lane, i) => {
    const o = ours[i]
    players.push(player(100, lane, o?.championId ?? pickOpponent(), o?.playerId ?? null))
    players.push(player(200, lane, pickOpponent(), null))
  })

  const team = (id: TeamId) => players.filter((p) => p.team === id)
  const sum = (id: TeamId, f: (p: LivePlayer) => number) => team(id).reduce((n, p) => n + f(p), 0)
  const dragonsTaken = Math.min(4, Math.floor(minutes / 6))
  const dragons: Record<TeamId, string[]> = { 100: [], 200: [] }
  for (let i = 0; i < dragonsTaken; i++) dragons[i % 3 === 2 ? 200 : 100].push(DRAGONS[(i * 2) % DRAGONS.length])

  const state: LiveState = {
    game_time: t,
    game_mode: 'CLASSIC',
    our_team: ours.length ? 100 : null,
    teams: {
      '100': {
        kills: sum(100, (p) => p.kills),
        gold: sum(100, (p) => p.item_gold),
        towers: Math.floor(minutes / 7),
        inhibitors: minutes > 28 ? 1 : 0,
        dragons: dragons[100],
        barons: minutes > 25 ? 1 : 0,
        heralds: minutes > 15 ? 1 : 0,
        grubs: minutes > 8 ? 4 : 0,
        atakhan: 0,
      },
      '200': {
        kills: sum(200, (p) => p.kills),
        gold: sum(200, (p) => p.item_gold),
        towers: Math.floor(minutes / 11),
        inhibitors: 0,
        dragons: dragons[200],
        barons: 0,
        heralds: 0,
        grubs: minutes > 8 ? 2 : 0,
        atakhan: 0,
      },
    },
    players,
    events: demoEvents(players, t),
    gold_history: [],
    result: null,
    notes: [],
  }

  // Gold lead graph: a wavy history that ends at the score bug's current lead.
  const now = state.teams['100'].gold - state.teams['200'].gold
  const points = Math.floor(t / 30) + 1
  state.gold_history = Array.from({ length: points }, (_, i) => {
    const s = i * 30
    const shape = (s / t) * (1 + 0.35 * Math.sin((3 * Math.PI * s) / t)) // wobbles, ends exactly at `now`
    return { t: s, diff: Math.round(now * shape) }
  })
  if (t % 30) state.gold_history.push({ t, diff: now })

  return {
    game_id: opts.gameId ?? 0,
    riot_game_id: null,
    platform: null,
    queue_id: 420,
    started_at: null,
    detected_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ended_at: null,
    our_team: state.our_team,
    participants: [],
    bans: [],
    state,
    streaming: true,
    // As the game client reports them: our players' lanes.
    roles: Object.fromEntries(
      players
        .filter((p) => p.player_id != null)
        .map((p) => [String(p.player_id), { role: p.position as Role, source: 'game' as const }]),
    ),
  }
}

/** A play-by-play up to `t`, newest first. */
function demoEvents(players: LivePlayer[], t: number): LiveEvent[] {
  const who = (p: LivePlayer | undefined) => (p ? { champion_id: p.champion_id, player_id: p.player_id } : null)
  const blue = players.filter((p) => p.team === 100)
  const red = players.filter((p) => p.team === 200)
  const script: LiveEvent[] = [
    { t: 205, type: 'first_blood', team: 100, killer: who(blue[2]) },
    { t: 205, type: 'kill', team: 100, killer: who(blue[2]), victim: who(red[2]) },
    { t: 330, type: 'grubs', team: 100, killer: who(blue[1]) },
    { t: 420, type: 'dragon', team: 100, killer: who(blue[1]), detail: 'Fire' },
    { t: 545, type: 'kill', team: 200, killer: who(red[3]), victim: who(blue[4]) },
    { t: 610, type: 'kill', team: 100, killer: who(blue[0]), victim: who(red[0]) },
    { t: 612, type: 'multikill', team: 100, killer: who(blue[0]), streak: 2 },
    { t: 780, type: 'tower', team: 100 },
    { t: 900, type: 'herald', team: 100, killer: who(blue[1]) },
    { t: 1020, type: 'dragon', team: 200, killer: who(red[1]), detail: 'Earth', stolen: true },
    { t: 1260, type: 'kill', team: 100, killer: who(blue[3]), victim: who(red[3]) },
    { t: 1500, type: 'baron', team: 100, killer: who(blue[1]) },
    { t: 1510, type: 'ace', team: 100 },
  ]
  return script.filter((e) => e.t <= t).reverse()
}
