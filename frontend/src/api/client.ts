import type {
  AppSettings,
  Champion,
  Game,
  Pick,
  Player,
  PoolEntry,
  ReviveToken,
  Run,
  SpinResult,
} from '../types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
      else if (Array.isArray(data.detail)) message = data.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* not JSON */
    }
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
  spin: (runId: number, playerIds: number[]) =>
    post<SpinResult>(`/runs/${runId}/spins`, { player_ids: playerIds }),

  games: (runId?: number) => get<Game[]>(`/games${qs({ run_id: runId })}`),
  game: (id: number) => get<Game>(`/games/${id}`),
  setPicks: (gameId: number, picks: Pick[]) => patch<Game>(`/games/${gameId}/assignments`, { picks }),
  setResult: (gameId: number, result: 'win' | 'loss' | 'void', reason?: string) =>
    post<Game>(`/games/${gameId}/result`, { result, reason }),
  undo: (gameId: number) => post<Game>(`/games/${gameId}/undo`),

  tokens: (params: { run_id?: number; player_id?: number; unused_only?: boolean }) =>
    get<ReviveToken[]>(`/tokens${qs(params)}`),
}
