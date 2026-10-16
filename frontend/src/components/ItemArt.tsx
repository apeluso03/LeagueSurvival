import type { CSSProperties } from 'react'
import { ITEM_META } from '../lib/items'
import type { ItemType } from '../types'

/** Square item icon in the style of League's item art: framed, lit from the middle. */
export function ItemArt({ type, size = 64, className = '' }: { type: ItemType; size?: number; className?: string }) {
  const meta = ITEM_META[type]
  return (
    <span
      className={`item-art ${className}`}
      style={{ width: size, height: size, ['--c' as string]: meta.color } as CSSProperties}
      aria-hidden
    >
      <meta.Icon width={Math.round(size * 0.46)} height={Math.round(size * 0.46)} strokeWidth={2} />
    </span>
  )
}
