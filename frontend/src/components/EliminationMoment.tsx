import { useEffect, type CSSProperties } from 'react'
import { createPortal } from 'react-dom'
import { useChampionMap, usePlayerMap } from '../hooks/queries'
import { loadingUrl } from '../lib/champions'
import { playShatter, playShieldSave } from '../lib/sound'
import type { Game } from '../types'
import { ShieldIcon } from './icons'
import { BroadcastBanner, ReplayChrome } from './ReplayChrome'

const STAGGER_MS = 140
const CRACK_MS = 760 // when each card cracks (and the sound plays), before its stagger
const END_MS = 2500 // when the last card has fallen apart

// A jagged split down the middle of the card (percent coordinates, top to bottom).
const CRACK = [
  [52, 0],
  [46, 17],
  [57, 33],
  [44, 51],
  [55, 67],
  [47, 84],
  [53, 100],
]
const pts = (list: number[][]) => list.map(([x, y]) => `${x}% ${y}%`).join(', ')
const LEFT = `polygon(0% 0%, ${pts(CRACK)}, 0% 100%)`
const RIGHT = `polygon(${pts(CRACK)}, 100% 100%, 100% 0%)`
const CRACK_LINE = CRACK.map(([x, y]) => `${x},${y}`).join(' ')

/**
 * The moment a loss lands: each eliminated champion's card flashes red, cracks with a thud and
 * falls apart; champs saved by a shield get a teal flash instead. Click or Esc skips it.
 */
export function EliminationMoment({ game, onDone }: { game: Game; onDone: () => void }) {
  const champs = useChampionMap()
  const players = usePlayerMap()
  const cards = [
    ...game.eliminated.map((id) => ({ id, saved: false })),
    ...game.shields_saved.map((id) => ({ id, saved: true })),
  ]
  const who = (cid: string) => {
    const a = game.assignments.find((x) => x.played_champion_id === cid)
    return a ? players.get(a.player_id)?.display_name : undefined
  }

  useEffect(() => {
    cards.forEach((c, i) => {
      const at = (CRACK_MS + i * STAGGER_MS) / 1000
      if (c.saved) playShieldSave(at)
      else playShatter(at)
    })
    const total = END_MS + (cards.length - 1) * STAGGER_MS
    const t = setTimeout(onDone, total)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onDone()
    window.addEventListener('keydown', onKey)
    return () => (clearTimeout(t), window.removeEventListener('keydown', onKey))
    // Plays once per game; the parent remounts this for a new one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [game.id])

  const lost = game.eliminated.length
  return createPortal(
    <div
      className="elim-overlay fixed inset-0 z-[80] flex flex-col items-center justify-center gap-6 bg-black/75 p-4"
      style={{ '--elim-total': `${END_MS + (cards.length - 1) * STAGGER_MS}ms` } as CSSProperties}
      onClick={onDone}
      role="dialog"
      aria-label={lost ? `${lost} champion${lost > 1 ? 's' : ''} eliminated` : 'Shield saved a champion'}
    >
      <ReplayChrome tag={`Replay · Game ${game.id}`} />
      <BroadcastBanner color={lost ? '#c8102e' : 'var(--color-hex-400)'}>
        <h2 className="elim-title font-display text-3xl tracking-[0.2em] text-white uppercase sm:text-5xl">{lost ? 'Eliminated' : 'Saved!'}</h2>
      </BroadcastBanner>
      <div className="flex max-w-4xl flex-wrap justify-center gap-4">
        {cards.map((c, i) => {
          const champ = champs.get(c.id)
          const art = champ ? loadingUrl({ champion_id: c.id, image_url: champ.image_url }) : null
          const style = { '--d': `${i * STAGGER_MS}ms`, backgroundImage: art ? `url(${art})` : undefined } as CSSProperties
          const by = who(c.id)
          return (
            <div key={c.id} className="flex flex-col items-center gap-2" style={{ '--d': `${i * STAGGER_MS}ms` } as CSSProperties}>
              <div className={`elim-card ${c.saved ? 'is-saved' : ''}`}>
                {c.saved ? (
                  <>
                    <div className="elim-half" style={style} />
                    <span className="elim-shield">
                      <ShieldIcon className="h-10 w-10" strokeWidth={2} />
                    </span>
                  </>
                ) : (
                  <>
                    <div className="elim-half elim-left" style={{ ...style, clipPath: LEFT }} />
                    <div className="elim-half elim-right" style={{ ...style, clipPath: RIGHT }} />
                    <svg className="elim-crack" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
                      <polyline points={CRACK_LINE} pathLength={1} />
                    </svg>
                    <span className="elim-flash" />
                  </>
                )}
              </div>
              <div className="elim-caption text-center">
                <div className="font-display font-bold text-gold-100">{champ?.name ?? c.id}</div>
                <div className={`text-xs ${c.saved ? 'text-hex-200' : 'text-red-300'}`}>
                  {c.saved ? 'Shield broke instead' : by ? `Lost by ${by}` : 'Eliminated'}
                </div>
              </div>
            </div>
          )
        })}
      </div>
      <p className="elim-caption text-xs text-slate-400">Click to skip</p>
    </div>,
    document.body,
  )
}
