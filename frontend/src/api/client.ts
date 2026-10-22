import type {
  Account,
  AppSettings,
  Invite,
  InviteInfo,
  LiveGame,
  Me,
  SiteInfo,
  SiteInvite,
  Champion,
  AchievementReport,
  ChampionLine,
  CompSuggestion,
  HallOfShame,
  MetaStatus,
  Wrapped,
  OptionFact,
  PlayerProfile,
  RunRecap,
  ChampionReport,
  Game,
  GoldInfo,
  InventoryItem,
  ItemType,
  ItemUse,
  PlayerEconomy,
  Shop,
  Pick,
  Player,
  PlayerStats,
  PoolEntry,
  PoolEvent,
  ReviveToken,
  RiotStatus,
  Role,
  Run,
  SpinResult,
  SyncResult,
} from '../types'

const UNREACHABLE = "Can't reach the backend. Is it running?"

export class ApiError extends Error {
  status: number
  /** True when the backend didn't answer at all (not running, or the dev proxy couldn't connect). */
  unreachable: boolean
  constructor(status: number, message: string, unreachable = false) {
    super(message)
    this.status = status
    this.unreachable = unreachable
  }
}

export const isUnreachable = (e: unknown) => e instanceof ApiError && e.unreachable

/** Called when the backend says the session is gone (signed out elsewhere, expired). */
let onSignedOut: (() => void) | null = null
export function setSignedOutHandler(fn: () => void) {
  onSignedOut = fn
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, UNREACHABLE, true)
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    let fromBackend = false
    try {
      const data = await res.json()
      fromBackend = true
      if (typeof data.detail === 'string') message = data.detail
      else if (Array.isArray(data.detail)) message = data.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* not JSON */
    }
    // The backend always answers errors with JSON; a bare 5xx means the dev proxy couldn't reach it.
    if (!fromBackend && res.status >= 500) throw new ApiError(res.status, UNREACHABLE, true)
    if (res.status === 401 && !path.startsWith('/auth/')) onSignedOut?.()
    throw new ApiError(res.status, message)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const get = <T>(path: string) => request<T>('GET', path)
const post = <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {})
const patch = <T>(path: string, body: unknown) => request<T>('PATCH', path, body)
const put = <T>(path: string, body: unknown) => request<T>('PUT', path, body)

function qs(params: Record<string, string | number | boolean | undefined>) {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined) as [string, string][]
  return entries.length ? `?${new URLSearchParams(entries)}` : ''
}

export const api = {
  me: () => get<Me>('/auth/me'),
  setUp: (body: { username: string; password: string; player_id: number | null }) => post<Me>('/auth/setup', body),
  login: (body: { username: string; password: string }) => post<Me>('/auth/login', body),
  logout: () => post<void>('/auth/logout'),
  changePassword: (body: { current_password: string; new_password: string }) => post<Me>('/auth/password', body),
  invite: (token: string) => get<InviteInfo>(`/auth/invites/${encodeURIComponent(token)}`),
  register: (body: { token: string; username: string; password: string }) => post<Me>('/auth/register', body),
  acceptInvite: (token: string) => post<Me>(`/auth/invites/${encodeURIComponent(token)}/accept`),
  signUp: (body: { username: string; password: string; group_name: string; code: string | null }) =>
    post<Me>('/auth/signup', body),
  startGroup: (body: { name: string; code: string | null }) => post<Me>('/groups', body),
  switchGroup: (groupId: number) => post<Me>(`/groups/${groupId}/switch`),
  renameGroup: (name: string) => patch<Me>('/groups/current', { name }),
  site: () => get<SiteInfo>('/site'),
  updateSite: (body: { open_signup: boolean }) => patch<SiteInfo>('/site', body),
  createSiteInvite: (note: string) => post<SiteInvite & { code: string }>('/site/invites', { note }),
  revokeSiteInvite: (id: number) => request<void>('DELETE', `/site/invites/${id}`),
  accounts: () => get<{ accounts: Account[]; invites: Invite[] }>('/accounts'),
  createInvite: (playerId: number) => post<Invite & { token: string }>('/accounts/invites', { player_id: playerId }),
  revokeInvite: (id: number) => request<void>('DELETE', `/accounts/invites/${id}`),
  deleteAccount: (id: number) => request<void>('DELETE', `/accounts/${id}`),
  forgetPlayer: (playerId: number) => post<{ ok: boolean }>(`/privacy/players/${playerId}/forget`),
  forgetPuuids: (puuids: string[]) => post<{ requested: number; players_forgotten: number }>('/privacy/forget', { puuids }),
  purgeRiotData: () => post<{ match_stats: number; matches: number }>('/privacy/purge', { confirm: 'DELETE' }),

  settings: () => get<AppSettings>('/settings'),
  updateSettings: (body: Partial<AppSettings> & { void_pending?: boolean }) =>
    patch<AppSettings>('/settings', body),

  players: () => get<Player[]>('/players'),
  createPlayer: (body: Partial<Player>) => post<Player>('/players', body),
  updatePlayer: (id: number, body: Partial<Player>) => patch<Player>(`/players/${id}`, body),
  deletePlayer: (id: number) => request<void>('DELETE', `/players/${id}`),
  linkPlayer: (id: number) => post<Player>(`/players/${id}/link`),

  riotStatus: (check = false) => get<RiotStatus>(`/riot/status${qs({ check })}`),
  sync: () => post<SyncResult>('/sync'),
  playerStats: (params: { run_id?: number; challenge_only: boolean }) =>
    get<PlayerStats[]>(`/stats/players${qs(params)}`),

  champions: () => get<Champion[]>('/champions'),
  refreshChampions: () => post<{ count: number }>('/champions/refresh'),
  championStats: (championId: string, runId?: number) =>
    get<ChampionReport>(`/champions/${championId}/stats${qs({ run_id: runId })}`),

  runs: () => get<Run[]>('/runs'),
  run: (id: number) => get<Run>(`/runs/${id}`),
  createRun: (body: {
    name: string
    options_per_player: 3 | 4
    champion_ids?: string[] | null
    owner_player_id?: number | null
  }) =>
    post<Run>('/runs', body),
  endRun: (id: number) => post<Run>(`/runs/${id}/end`),
  deleteRun: (id: number) => request<void>('DELETE', `/runs/${id}`),
  pool: (runId: number, includeEliminated = true) =>
    get<PoolEntry[]>(`/runs/${runId}/pool${qs({ include_eliminated: includeEliminated })}`),
  recap: (runId: number) => get<RunRecap>(`/runs/${runId}/recap`),
  profile: (playerId: number, runId?: number | null) =>
    get<PlayerProfile>(`/players/${playerId}/profile${qs({ run_id: runId ?? undefined })}`),
  optionFacts: (gameId: number) => get<Record<string, Record<string, OptionFact>>>(`/games/${gameId}/option-facts`),
  achievements: () => get<AchievementReport>('/achievements'),
  shame: (runId?: number | null) => get<HallOfShame>(`/shame${qs({ run_id: runId ?? undefined })}`),
  wrapped: (month?: string) => get<Wrapped>(`/wrapped${qs({ month })}`),
  metaStatus: () => get<MetaStatus>('/meta/status'),
  refreshPositions: () => post<{ count: number }>('/meta/positions/refresh'),
  comp: (championIds: string[], exclude: string[] = [], roles: Record<string, Role> = {}) =>
    post<CompSuggestion>('/comp', { champion_ids: championIds, exclude, roles }),
  championLines: (runId: number) => get<Record<string, ChampionLine>>(`/runs/${runId}/champion-lines`),
  eliminate: (runId: number, championId: string) => post<Run>(`/runs/${runId}/pool/${championId}/eliminate`),
  revive: (runId: number, championId: string, tokenId?: number) =>
    post<Run>(`/runs/${runId}/pool/${championId}/revive`, { token_id: tokenId ?? null }),
  events: (runId: number) => get<PoolEvent[]>(`/runs/${runId}/events`),
  spin: (runId: number, playerIds: number[]) =>
    post<SpinResult>(`/runs/${runId}/spins`, { player_ids: playerIds }),

  games: (runId?: number) => get<Game[]>(`/games${qs({ run_id: runId })}`),
  game: (id: number) => get<Game>(`/games/${id}`),
  setPicks: (gameId: number, picks: Pick[]) => patch<Game>(`/games/${gameId}/assignments`, { picks }),
  setRole: (gameId: number, playerId: number, role: Role | null) =>
    put<Game>(`/games/${gameId}/role`, { player_id: playerId, role }),
  setResult: (gameId: number, result: 'win' | 'loss' | 'void', reason?: string) =>
    post<Game>(`/games/${gameId}/result`, { result, reason }),
  undo: (gameId: number) => post<Game>(`/games/${gameId}/undo`),
  linkMatch: (gameId: number, matchId: string) => post<Game>(`/games/${gameId}/link-match`, { riot_match_id: matchId }),

  shop: (runId: number) => get<Shop>(`/runs/${runId}/shop`),
  updateShopConfig: (runId: number, body: Record<string, unknown>) => patch<Shop>(`/runs/${runId}/shop-config`, body),
  economy: (runId: number) => get<PlayerEconomy[]>(`/runs/${runId}/economy`),
  gold: (runId: number, playerId: number) => get<GoldInfo>(`/runs/${runId}/players/${playerId}/gold`),
  adjustGold: (runId: number, playerId: number, amount: number, note?: string) =>
    post<GoldInfo>(`/runs/${runId}/players/${playerId}/gold/adjust`, { amount, note }),
  inventory: (runId: number, playerId: number) => get<InventoryItem[]>(`/runs/${runId}/players/${playerId}/inventory`),
  purchase: (runId: number, playerId: number, type: ItemType) =>
    post<{ item: InventoryItem; balance: number }>(`/runs/${runId}/players/${playerId}/purchase`, { type }),
  useItem: (itemId: number, body: ItemUse) => post<InventoryItem>(`/items/${itemId}/use`, body),
  review: (gameId: number, action: 'accept' | 'reject') => post<Game>(`/games/${gameId}/review`, { action }),

  live: () => get<{ game_id: number | null; live: LiveGame | null }>('/live'),
  gameLive: (gameId: number) => get<{ game_id: number; live: LiveGame | null }>(`/games/${gameId}/live`),

  tokens: (params: { run_id?: number; player_id?: number; unused_only?: boolean }) =>
    get<ReviveToken[]>(`/tokens${qs(params)}`),
}
