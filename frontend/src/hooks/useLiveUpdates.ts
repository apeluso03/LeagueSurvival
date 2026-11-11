import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useSyncExternalStore } from 'react'
import { connectLive, isLiveConnected, onLiveEvent, subscribeConnection, type LiveEvent } from '../lib/liveUpdates'

// Never refetched on a live event: the champion list doesn't change, and builds are slow to work out.
const KEEP = new Set(['champions', 'comp'])

/** Keeps this tab's live-updates socket open for the group it's viewing (mount once, in the layout). */
export function useLiveUpdatesConnection(groupId: number | null | undefined) {
  const qc = useQueryClient()
  useEffect(() => {
    if (groupId == null) return
    return connectLive(() => void qc.invalidateQueries({ predicate: (q) => !KEEP.has(String(q.queryKey[0])) }))
  }, [qc, groupId])
}

/** True while the socket is open. Polling can stop then: changes arrive as they happen. */
export const useLiveConnected = () => useSyncExternalStore(subscribeConnection, isLiveConnected, () => false)

/** Run `fn` for every live event caused by someone else (another person, tab or the backend). */
export function useLiveEvent(fn: (e: LiveEvent) => void) {
  const ref = useRef(fn)
  useEffect(() => {
    ref.current = fn
  })
  useEffect(() => onLiveEvent((e) => ref.current(e)), [])
}
