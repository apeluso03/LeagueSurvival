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
}

export interface Assignment {
  player_id: number
  options: string[]
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
}
