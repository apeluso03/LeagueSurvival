import { dangerInfo } from '../lib/danger'

const TONE = {
  safe: { bar: 'var(--color-hex-300)', text: 'text-slate-400' },
  warning: { bar: '#e3a53b', text: 'text-amber-200' },
  danger: { bar: '#e0434f', text: 'text-red-300' },
}

/** How many champions are left versus how many a spin needs, and how many losses that leaves. */
export function DangerMeter({
  alive,
  total,
  players,
  options,
  tokens,
}: {
  alive: number
  total: number
  players: number
  options: number
  tokens: number
}) {
  const d = dangerInfo(alive, players, options)
  const tone = TONE[d.level]
  const at = (n: number) => `${Math.min(100, (n / Math.max(total, 1)) * 100)}%`
  let text: string
  if (d.lossesUntilBlocked < 0) text = `Not enough champs left for ${players} players.`
  else if (d.lossesUntilShrink < 0)
    text = `Options are already shrinking. ${d.lossesUntilBlocked} more loss${d.lossesUntilBlocked === 1 ? '' : 'es'} and you can't spin.`
  else
    text = `${d.lossesUntilShrink} more loss${d.lossesUntilShrink === 1 ? '' : 'es'} before options start to shrink (${players} players need ${d.full} champs).`
  return (
    <div className="flex flex-col gap-1.5" aria-label="Champions left">
      <div className="relative h-2.5 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full transition-[width] duration-500" style={{ width: at(alive), background: tone.bar }} />
        <span className="absolute inset-y-0 w-0.5 bg-slate-100/70" style={{ left: at(d.full) }} title={`${d.full}: full options`} />
        <span className="absolute inset-y-0 w-0.5 bg-red-400" style={{ left: at(d.minimum) }} title={`${d.minimum}: can't spin below this`} />
      </div>
      <p className={`text-xs ${tone.text}`}>
        <b className="text-slate-200">{alive}</b> of {total} champs left · {text}
        {tokens > 0 && d.level !== 'safe' && <span className="text-gold-300"> You have {tokens} revive token{tokens > 1 ? 's' : ''}.</span>}
      </p>
    </div>
  )
}
