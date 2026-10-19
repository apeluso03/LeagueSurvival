import type { Role } from '../types'

/**
 * Mobalytics build widgets (github.com/mobalyticshq/mobalytics-widgets, MIT).
 * Their champion slug is the Data Dragon id in lower case: "MonkeyKing" -> "monkeyking",
 * "Nunu" (Nunu & Willump) -> "nunu", "Renata" (Renata Glasc) -> "renata".
 */
// Our fixed copy of their script (scripts/update_mobalytics.py): theirs loads only the first 400
// items of Mobalytics' item catalog, which no longer includes the normal items, so no item icons.
export const MOBA_SCRIPT_PATH = '/vendor/mobalytics-widgets.js'

export const mobaSlug = (championId: string) => championId.toLowerCase()

const ROLE: Record<Role, string> = { TOP: 'TOP', JUNGLE: 'JUNGLE', MIDDLE: 'MID', BOTTOM: 'ADC', UTILITY: 'SUPPORT' }
export const mobaRole = (role: Role | null | undefined) => (role ? ROLE[role] : undefined)

export const mobaBuildUrl = (championId: string) => `https://mobalytics.gg/lol/champions/${mobaSlug(championId)}/build`

/** Only letters and digits reach the widget page's HTML. */
const safe = (s: string) => s.replace(/[^a-z0-9_-]/gi, '')

/**
 * The page that runs inside the sandboxed frame: one widget, Mobalytics' script, and a few lines
 * that tell the parent how tall the widget is so the frame can fit it.
 */
export function widgetPage(opts: { championId: string; role?: string; compact?: boolean; frameId: string }): string {
  const attrs = [
    `data-moba-widget="${opts.compact ? 'lol-champion-build-compact' : 'lol-champion-build'}"`,
    `data-moba-champion="${safe(mobaSlug(opts.championId))}"`,
    opts.role ? `data-moba-champion-role="${safe(opts.role)}"` : '',
  ].join(' ')
  // no-referrer: Mobalytics' image server answers 403 to any Referer but its own site (hotlink
  // protection), which blanked every icon. Without one it serves them (and learns less about us).
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><base target="_blank">
<style>html,body{margin:0;padding:0;background:transparent;overflow:hidden}</style></head>
<body><div ${attrs}></div>
<script>
  var last = 0
  function report() {
    var h = Math.ceil(document.documentElement.scrollHeight)
    if (h !== last) { last = h; parent.postMessage({ mobaFrame: ${JSON.stringify(safe(opts.frameId))}, height: h }, '*') }
  }
  new ResizeObserver(report).observe(document.body)
  setInterval(report, 1000)
</script>
<script async src="${window.location.origin}${MOBA_SCRIPT_PATH}"></script>
</body></html>`
}
