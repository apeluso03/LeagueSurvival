/**
 * Warm the browser's image cache and decode champion portraits during idle time, so a spin
 * doesn't stall decoding a few hundred images in its first frames.
 */
const decoded = new Map<string, HTMLImageElement>() // kept alive so the decoded bitmaps stay cached
const BATCH = 16

type IdleWindow = Window & {
  requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number
}

export function preloadImages(urls: string[]): () => void {
  const todo = urls.filter((u) => u && !decoded.has(u))
  let cancelled = false
  const w = window as IdleWindow
  const schedule = (fn: () => void) =>
    w.requestIdleCallback ? w.requestIdleCallback(fn, { timeout: 1500 }) : window.setTimeout(fn, 50)

  const next = () => {
    if (cancelled || !todo.length) return
    for (const url of todo.splice(0, BATCH)) {
      const img = new Image()
      img.decoding = 'async'
      img.src = url
      decoded.set(url, img)
      img.decode?.().catch(() => decoded.delete(url))
    }
    schedule(next)
  }
  schedule(next)
  return () => {
    cancelled = true
  }
}
