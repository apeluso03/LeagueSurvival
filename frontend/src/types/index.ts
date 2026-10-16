// Mirrors backend/app/schemas and backend/app/models.

export interface AppSettings {
  challenge_mode: boolean
  active_run_id: number | null
  allowed_queue_ids: number[]
  poll_interval_seconds: number
  remake_threshold_seconds: number
  last_used_player_ids: number[]
  riot_api_key_set: boolean
  meta_crawl: boolean
  meta_platform: string
  meta_region: string
}

export interface Player {
  id: number
  display_name: string
  riot_game_name: string | null
  riot_tag_line: string | null
  puuid: string | null
  platform: string
  region: string
  created_at: string
  color: string | null // broadcast team colour; null = the default for their id
  title: string | null // achievement id whose title they show
  link_error?: string | null
  username: string | null // the account that plays as this player, if anyone has signed up
}

export interface Champion {
  id: string
  key: number
  name: string
  title: string
  tags: string[]
  image_url: string
  ddragon_version: string
}

export interface Run {
  id: number
  name: string
  status: 'active' | 'ended'
  options_per_player: 3 | 4
  win_count: number
  current_streak: number
  best_streak: number
  started_at: string
  ended_at: string | null
  alive_count: number
  total_count: number
  tokens_available: number
  pending_game_id: number | null
  games_played: number
  owner_player_id: number | null
  owner_user_id: number | null // the account that runs spins, results and settings for this run
  lobby_code: string | null
  shielded_count: number
}

export interface PoolEntry {
  champion_id: string
  key: number
  name: string
  title: string
  tags: string[]
  image_url: string
  status: 'alive' | 'eliminated'
  eliminated_at: string | null
  eliminated_in_game_id: number | null
  eliminated_by_player_id: number | null
  shield_item_id: number | null
  shield_player_id: number | null
}

/** A champion's short numbers for one run (Pool cards). */
export interface ChampionLine {
  offered: number
  played: number
  wins: number
  losses: number
  on_spin: number[] // players with it in the pending spin
  blacklisted_by: number[] // players with it on an armed blacklist
}

/** Short numbers under a rolled champion on the Wheels tab. */
export interface OptionFact {
  you_games: number
  you_wins: number
  riot_games: number
  riot_wins: number
  group_games: number
  group_wins: number
}

export interface Assignment {
  player_id: number
  options: string[]
  original_options?: string[]
  played_champion_id: string | null
  played_option_index: number | null
}

export type GameStatus = 'pending' | 'won' | 'lost' | 'void'

export interface Game {
  id: number
  run_id: number
  created_at: string
  status: GameStatus
  result_source: 'auto' | 'manual' | null
  riot_match_id: string | null
  resolved_at: string | null
  void_reason: string | null
  assignments: Assignment[]
  eliminated: string[]
  tokens_earned: number[]
  needs_review: boolean
  review_reason: string | null
  match: MatchSummary | null
  gold: Record<string, number> // player id -> gold from this game
  grades: Record<string, string> // player id -> rating grade
  items_used: { player_id: number; type: ItemType; target: Record<string, unknown> }[]
  shields_saved: string[]
  contracts: { player_id: number; description: string; status: string; payout: number }[]
}

export interface MatchPlayer {
  player_id: number
  champion_id: string | null
  team_id: number
  win: boolean
  kills: number
  deaths: number
  assists: number
  in_options: boolean
}

export interface MatchSummary {
  match_id: string
  queue_id: number
  game_start: string | null
  game_duration: number
  early_surrender: boolean
  players: MatchPlayer[]
}

export interface SpinResult {
  practice: boolean
  game: Game | null
  assignments: Assignment[]
}

export interface Pick {
  player_id: number
  option_index?: number | null
  champion_id?: string | null
}

export interface ReviveToken {
  id: number
  run_id: number
  player_id: number
  earned_in_game_id: number
  used_at: string | null
  revived_champion_id: string | null
}

export interface RiotStatus {
  key_set: boolean
  key_valid: boolean | null
  message: string | null
  last_sync_at: string | null
  last_sync_error: string | null
}

export interface MatchOutcome {
  game_id: number
  status: 'applied' | 'voided' | 'needs_review' | 'waiting' | 'unlinked' | 'linked' | 'skipped'
  message: string
  match_id: string | null
}

export interface SyncResult {
  players_synced: number
  new_matches: number
  errors: string[]
  games: MatchOutcome[]
}

export interface ChampionStats {
  champion_id: string
  games: number
  wins: number
  win_rate: number
  kda: number | null
}

export interface PlayerStats {
  player_id: number
  games: number
  wins: number
  losses: number
  win_rate: number | null
  detailed_games: number
  avg_kills: number | null
  avg_deaths: number | null
  avg_assists: number | null
  kda: number | null
  kill_participation: number | null
  cs_per_min: number | null
  damage_per_min: number | null
  vision_per_min: number | null
  best_champions: ChampionStats[]
  eliminated_champions: string[]
  avg_grade: string | null
  gold_balance: number | null
  gold_earned: number | null
  gold_spent: number | null
}

export interface PoolEvent {
  id: number
  run_id: number
  game_id: number | null
  type: 'eliminate' | 'revive' | 'manual_eliminate' | 'manual_revive'
  champion_id: string | null
  player_id: number | null
  token_id: number | null
  created_at: string
  undone: boolean
}

export interface PlayerChampionLine {
  player_id: number
  games: number
  wins: number
}

export interface ChampionReport {
  champion_id: string
  in_run: boolean
  status: 'alive' | 'eliminated' | null
  eliminated_at: string | null
  eliminated_by_player_id: number | null
  eliminated_in_game_id: number | null
  times_offered: number
  times_played: number
  wins: number
  losses: number
  played_by: PlayerChampionLine[]
  all_runs_played: number
  all_runs_wins: number
  riot_games: number
  riot_wins: number
  riot_kda: number | null
  riot_players: PlayerChampionLine[]
}

// --- gold and shop (SPEC 7.7 to 7.9) ---

export type ItemType = 'reroll' | 'blacklist' | 'swap' | 'shield' | 'choose' | 'contract'

export interface ShopItem {
  type: ItemType
  name: string
  price: number
  when: string
  description: string
}

export interface ShopConfig {
  prices: Record<ItemType, number>
  gold: Record<string, number | string>
  contract: { payout: number; kills: number; assists: number; rating: string }
  blacklist_pct: number
}

export interface Shop {
  items: ShopItem[]
  blacklist_cap: number
  contract_payout: number
  config: ShopConfig
}

export interface ContractInfo {
  goal_type: 'kills' | 'assists' | 'win' | 'rating'
  target: string
  payout: number
  status: 'pending' | 'won' | 'lost' | 'refunded'
  game_id: number | null
  description: string
}

export interface InventoryItem {
  id: number
  player_id: number
  type: ItemType
  status: 'unused' | 'armed' | 'active' | 'used' | 'refunded'
  price_paid: number
  purchased_at: string
  used_at: string | null
  used_in_game_id: number | null
  target: Record<string, unknown>
  contract: ContractInfo | null
}

export interface LedgerRow {
  id: number
  amount: number
  reason: 'game' | 'contract_payout' | 'purchase' | 'refund' | 'manual_adjust'
  game_id: number | null
  item_id: number | null
  breakdown: Record<string, unknown>
  created_at: string
  undone: boolean
}

export interface GoldInfo {
  balance: number
  earned: number
  spent: number
  ledger: LedgerRow[]
}

export interface PlayerEconomy {
  player_id: number
  balance: number
  earned: number
  spent: number
  unused: Partial<Record<ItemType, number>>
  armed_blacklist: string[] | null
  active_contract: ContractInfo | null
}

export interface ItemUse {
  champion_id?: string
  game_id?: number
  other_player_id?: number
  champion_ids?: string[]
}

// --- run recap and player profile ---------------------------------------------------------

export interface RecapPlayer extends Omit<PlayerStats, 'best_champions' | 'eliminated_champions'> {
  eliminations: number
  tokens_earned: number
  multikills: { penta: number; quadra: number; triple: number; double: number }
  best_champion: ChampionStats | null
  top_champion: string | null // most played this run
}

export interface RecapAward {
  id: string
  title: string
  text: string
  player_id: number | null
  champion_id: string | null
}

export interface RunRecap {
  run: { id: number; name: string; status: 'active' | 'ended'; started_at: string; ended_at: string | null }
  totals: {
    games: number
    wins: number
    losses: number
    best_streak: number
    alive: number
    total: number
    tokens_earned: number
    tokens_used: number
    shields_saved: number
    items_bought: number
    gold_earned: number
    gold_spent: number
  }
  timeline: { game_id: number; status: 'won' | 'lost'; created_at: string }[]
  players: RecapPlayer[]
  awards: RecapAward[]
}

export interface ProfileGame {
  game_id: number
  run_id: number
  created_at: string
  status: 'won' | 'lost'
  champion_id: string | null
  options: string[]
  grade: string | null
  kda: [number, number, number] | null
  gold: number | null
  eliminated: boolean
  token_earned: boolean
}

export interface PlayerProfile {
  player: { id: number; display_name: string; riot_id: string | null; linked: boolean }
  stats: PlayerStats
  champions: { champion_id: string; games: number; wins: number }[]
  games: ProfileGame[]
  runs: { run_id: number; name: string; status: 'active' | 'ended'; games: number; wins: number }[]
  // Private: null unless it's your own player (or you run this run).
  items: Partial<Record<ItemType, { bought: number; used: number }>> | null
  gold_timeline: { at: string; balance: number; amount: number; reason: string }[] | null
  tokens_earned: number
}

// --- accounts ---------------------------------------------------------------------------------

export interface MeUser {
  id: number
  username: string
  player_id: number | null
  is_admin: boolean // the site owner
}

export interface Me {
  user: MeUser | null
  setup_needed: boolean
  players: { id: number; display_name: string }[] // only while setting up
}

export interface Account {
  id: number
  username: string
  player_id: number | null
  is_admin: boolean
  created_at: string
  last_login_at: string | null
}

export interface Invite {
  id: number
  player_id: number
  created_at: string
  expires_at: string
}

export interface InviteInfo {
  player_id: number
  display_name: string
  expires_at: string
}

// --- trophies, hall of shame, wrapped -------------------------------------------------------

export interface AchievementInfo {
  id: string
  name: string
  description: string
  title: string
  icon: string
  tier: 'bronze' | 'silver' | 'gold' | 'prismatic'
}

export interface AchievementUnlock {
  id: string
  game_id: number | null
  at: string
}

export interface AchievementReport {
  catalog: AchievementInfo[]
  rarity: Record<string, number> // share of players who have it, 0..1
  players: Record<string, AchievementUnlock[]>
}

export interface ShameGame {
  game_id: number
  run_id: number
  player_id: number
  champion_id: string | null
  won: boolean
  kills: number | null
  deaths: number | null
  assists: number | null
  kda: number | null
  duration: number | null
  at: string
}

export interface HallOfShame {
  worst_games: ShameGame[]
  most_deaths: ShameGame[]
  fastest_losses: ShameGame[]
  cursed_champions: { champion_id: string; games: number; wins: number }[]
  feeders: { player_id: number; games: number; deaths: number; avg_deaths: number }[]
  reapers: { player_id: number; champions_lost: number }[]
  wasted_items: { player_id: number; items: number; gold: number }[]
}

export interface WrappedPlayer {
  player_id: number
  games: number
  wins: number
  kda: number | null
  kills: number | null
  deaths: number | null
  avg_deaths: number | null
  pentas: number
  top_champion: string | null
  top_champion_games: number
  champions_lost: number
  gold_spent: number
  reroll_gold: number
}

export interface Wrapped {
  month: string
  months: string[]
  games: number
  wins: number
  best_streak: number
  champions_lost: number
  gold_spent: number
  reroll_gold: number
  items_bought: number
  pentas: number
  most_played: { champion_id: string; games: number; wins: number } | null
  mvp: WrappedPlayer | null
  feeder: WrappedPlayer | null
  top_killer: WrappedPlayer | null
  best_duo: { players: number[]; games: number; wins: number } | null
  worst_duo: { players: number[]; games: number; wins: number } | null
  worst_game: ShameGame | null
  best_game: ShameGame | null
  players: WrappedPlayer[]
}

// --- high-elo meta: comp suggestions ---------------------------------------------------------

export type Role = 'TOP' | 'JUNGLE' | 'MIDDLE' | 'BOTTOM' | 'UTILITY'

export interface RuneRef {
  id: number
  name: string
  icon?: string | null
}

export interface RunePage {
  primary: RuneRef
  keystone: RuneRef | null
  primary_perks: RuneRef[]
  secondary: RuneRef
  secondary_perks: RuneRef[]
  shards: { id: number; name: string }[]
  games: number
  win_rate: number | null
}

export interface MetaItemInfo {
  id: number
  name: string
  image: string | null
  games: number
  pick_rate: number | null
  win_rate: number | null
}

export interface CompPick {
  champion_id: string
  role: Role
  role_name: string
  role_source: 'high-elo' | 'positions'
  role_games: number
  role_win_rate: number | null
  off_role: boolean // rarely played in this role; the build comes from build_role
  build_role: Role | null
  runes: RunePage | null
  items: MetaItemInfo[]
  boots: MetaItemInfo | null
}

export interface CompSuggestion {
  patches: string[]
  matches: number
  picks: CompPick[]
}

export interface MetaStatus {
  enabled: boolean
  key_set: boolean
  platform: string
  patches: string[]
  matches: number
  champions_covered: number
  ladder_size: number
  ladder_position: number
  last_run_at: string | null
  last_error: string | null
}
