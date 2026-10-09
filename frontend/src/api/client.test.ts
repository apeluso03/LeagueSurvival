import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, isUnreachable } from './client'

const mockFetch = (impl: () => Promise<Response>) => vi.stubGlobal('fetch', vi.fn(impl))

afterEach(() => vi.unstubAllGlobals())

describe('api error handling', () => {
  it('uses the backend detail message', async () => {
    mockFetch(async () => new Response(JSON.stringify({ detail: 'Game 3 is still pending' }), { status: 409 }))
    const err = await api.settings().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.message).toBe('Game 3 is still pending')
    expect(isUnreachable(err)).toBe(false)
  })

  it('flags a network failure as unreachable', async () => {
    mockFetch(async () => {
      throw new TypeError('Failed to fetch')
    })
    expect(isUnreachable(await api.settings().catch((e) => e))).toBe(true)
  })

  it('flags a bare 5xx from the dev proxy as unreachable', async () => {
    mockFetch(async () => new Response('', { status: 500 }))
    expect(isUnreachable(await api.settings().catch((e) => e))).toBe(true)
  })

  it('keeps a JSON 5xx from the backend as a normal error', async () => {
    mockFetch(async () => new Response(JSON.stringify({ detail: 'Could not reach Data Dragon' }), { status: 502 }))
    const err = await api.refreshChampions().catch((e) => e)
    expect(isUnreachable(err)).toBe(false)
    expect(err.message).toBe('Could not reach Data Dragon')
  })
})
