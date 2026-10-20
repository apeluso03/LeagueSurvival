import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { mobaBuildUrl, mobaRole, widgetPage } from '../lib/mobalytics'
import type { Role } from '../types'
import { Spinner } from './ui'

/**
 * A Mobalytics build widget in a sandboxed frame. The frame gets its own throwaway origin
 * (no allow-same-origin), so Mobalytics' script can't read the page, our cookies, or call our API
 * as the signed-in user. It only loads when this component mounts, so nothing is sent to
 * Mobalytics until someone opens it.
 */
export function MobaWidget({ championId, role, compact = false }: { championId: string; role?: Role | null; compact?: boolean }) {
  const frameId = useId().replace(/[^a-z0-9]/gi, '')
  const ref = useRef<HTMLIFrameElement>(null)
  const [height, setHeight] = useState<number | null>(null)
  const srcDoc = useMemo(
    () => widgetPage({ championId, role: mobaRole(role), compact, frameId }),
    [championId, role, compact, frameId],
  )

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.source !== ref.current?.contentWindow) return // only our own frame
      const d = e.data as { mobaFrame?: string; height?: number }
      if (d?.mobaFrame === frameId && typeof d.height === 'number' && d.height > 40) setHeight(Math.min(d.height, 3000))
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [frameId])

  return (
    <div className="relative">
      {height == null && (
        <div className="flex items-center justify-center gap-2 py-10 text-xs text-slate-400">
          <Spinner className="h-4 w-4" /> Loading the Mobalytics build...
        </div>
      )}
      <iframe
        ref={ref}
        title={`Mobalytics build for ${championId}`}
        srcDoc={srcDoc}
        sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
        referrerPolicy="no-referrer"
        className="block w-full border-0"
        style={{ height: height ?? 1, opacity: height == null ? 0 : 1 }}
      />
      <a
        href={mobaBuildUrl(championId)}
        target="_blank"
        rel="noreferrer"
        className="mt-1 inline-block text-[11px] text-slate-400 underline hover:text-slate-200"
      >
        Open on Mobalytics
      </a>
    </div>
  )
}
