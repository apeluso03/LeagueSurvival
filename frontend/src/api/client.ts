import type {
  AppSettings,
  Champion,
  Game,
  Pick,
  Player,
  PlayerStats,
  PoolEntry,
  PoolEvent,
  ReviveToken,
  RiotStatus,
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
    throw new ApiError(res.status, message)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const get = <T>(path: string) => request<T>('GET', path)
const post = <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {})
const patch = <T>(path: string, body: unknown) => request<T>('PATCH', path, body)

function qs(params: Record<string, string | number | boolean | undefined>) {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined) as [string, string][]
  return entries.length ? `?${new URLSearchParams(entries)}` : ''
}

export const api = {
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

  runs: () => get<Run[]>('/runs'),
  run: (id: number) => get<Run>(`/runs/${id}`),
  createRun: (body: { name: string; options_per_player: 3 | 4; champion_ids?: string[] | null }) =>
    post<Run>('/runs', body),
  endRun: (id: number) => post<Run>(`/runs/${id}/end`),
  pool: (runId: number, includeEliminated = true) =>
    get<PoolEntry[]>(`/runs/${runId}/pool${qs({ include_eliminated: includeEliminated })}`),
  eliminate: (runId: number, championId: string) => post<Run>(`/runs/${runId}/pool/${championId}/eliminate`),
  revive: (runId: number, championId: string, tokenId?: number) =>
    post<Run>(`/runs/${runId}/pool/${championId}/revive`, { token_id: tokenId ?? null }),
  events: (runId: number) => get<PoolEvent[]>(`/runs/${runId}/events`),
  spin: (runId: number, playerIds: number[]) =>
    post<SpinResult>(`/runs/${runId}/spins`, { player_ids: playerIds }),

  games: (runId?: number) => get<Game[]>(`/games${qs({ run_id: runId })}`),
  game: (id: number) => get<Game>(`/games/${id}`),
  setPicks: (gameId: number, picks: Pick[]) => patch<Game>(`/games/${gameId}/assignments`, { picks }),
  setResult: (gameId: number, result: 'win' | 'loss' | 'void', reason?: string) =>
    post<Game>(`/games/${gameId}/result`, { result, reason }),
  undo: (gameId: number) => post<Game>(`/games/${gameId}/undo`),
  review: (gameId: number, action: 'accept' | 'reject') => post<Game>(`/games/${gameId}/review`, { action }),

  tokens: (params: { run_id?: number; player_id?: number; unused_only?: boolean }) =>
    get<ReviveToken[]>(`/tokens${qs(params)}`),
}
