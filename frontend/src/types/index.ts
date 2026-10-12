// Mirrors backend/app/schemas and backend/app/models.

export interface AppSettings {
  challenge_mode: boolean
  active_run_id: number | null
  allowed_queue_ids: number[]
  poll_interval_seconds: number
  remake_threshold_seconds: number
  last_used_player_ids: number[]
  riot_api_key_set: boolean
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
  link_error?: string | null
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
