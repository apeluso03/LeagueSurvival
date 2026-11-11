/**
 * Live updates (SPEC 12.3): one WebSocket per tab to /api/ws. The backend says what changed in the
 * group (a spin, picks, a result, or just "changed"), and this refreshes the matching data, so every
 * device shows the same thing within a moment. Pages can also listen for events (the Wheels tab
 * plays a spin's reels when someone else spins).
 */

export type LiveEvent = {
  type: string
  game_id?: number
  run_id?: number
  origin?: string | null
}

function makeId() {
  try {
    return crypto.randomUUID()
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  }
}

/** This tab's id. Sent with every request, so the tab can skip events it caused itself. */
export const CLIENT_ID = makeId()

type Listener = (e: LiveEvent) => void
const listeners = new Set<Listener>()
const connListeners = new Set<() => void>()
let connected = false

export function onLiveEvent(fn: Listener): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export const isLiveConnected = () => connected

export function subscribeConnection(fn: () => void): () => void {
  connListeners.add(fn)
  return () => connListeners.delete(fn)
}

function setConnected(v: boolean) {
  if (connected === v) return
  connected = v
  connListeners.forEach((fn) => fn())
}

// --- refreshing ---------------------------------------------------------------------------

let refresh: () => void = () => {}
let pauses = 0
let owed = false
let timer: ReturnType<typeof setTimeout> | null = null

/** Hold refreshes while something smooth is on screen (the spin reels); they happen after. */
export function pauseRefresh(): () => void {
  pauses++
  let done = false
  return () => {
    if (done) return
    done = true
    pauses--
    if (pauses === 0 && owed) scheduleRefresh()
  }
}

function scheduleRefresh() {
  owed = true
  if (pauses > 0 || timer) return
  // A change usually comes as a few messages at once (the event, then "changed"): refresh once.
  timer = setTimeout(() => {
    timer = null
    if (pauses > 0) return
    owed = false
    refresh()
  }, 200)
}

// --- the socket ---------------------------------------------------------------------------

const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000, 30000]

/**
 * Keep the socket open while signed in. `onRefresh` refetches everything that may have changed.
 * Returns a function that closes it. Reconnects on its own (and refreshes once, to catch up).
 */
export function connectLive(onRefresh: () => void): () => void {
  refresh = onRefresh
  let ws: WebSocket | null = null
  let attempt = 0
  let stopped = false
  let retry: ReturnType<typeof setTimeout> | null = null
  let everConnected = false

  const open = () => {
    if (stopped || typeof WebSocket === 'undefined') return
    const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/ws`
    try {
      ws = new WebSocket(url)
    } catch {
      return later()
    }
    ws.onmessage = (m) => {
      let e: LiveEvent
      try {
        e = JSON.parse(m.data)
      } catch {
        return
      }
      if (e.type === 'hello') {
        attempt = 0
        setConnected(true)
        if (everConnected) scheduleRefresh() // missed changes while away
        everConnected = true
        return
      }
      if (e.type === 'ping' || e.origin === CLIENT_ID) return
      listeners.forEach((fn) => fn(e))
      scheduleRefresh()
    }
    ws.onclose = (ev) => {
      ws = null
      setConnected(false)
      if (stopped || ev.code === 4401) return // signed out: the app takes over from here
      later(ev.code === 4409 ? 0 : undefined)
    }
  }

  const later = (ms?: number) => {
    if (stopped || retry) return
    const wait = ms ?? BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]
    attempt++
    retry = setTimeout(() => {
      retry = null
      open()
    }, wait)
  }

  // Back online or back on the tab: try again right away instead of waiting out the backoff.
  const wake = () => {
    if (ws || stopped || document.visibilityState === 'hidden') return
    if (retry) clearTimeout(retry)
    retry = null
    attempt = 0
    open()
  }
  window.addEventListener('online', wake)
  document.addEventListener('visibilitychange', wake)
  open()

  return () => {
    stopped = true
    if (retry) clearTimeout(retry)
    window.removeEventListener('online', wake)
    document.removeEventListener('visibilitychange', wake)
    ws?.close()
    setConnected(false)
  }
}
