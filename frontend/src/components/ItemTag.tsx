import { ITEM_META } from '../lib/items'
import type { ItemType } from '../types'

/** Small icon for an item type, for use elsewhere (Wheels, History). */
export function ItemTag({ type }: { type: ItemType }) {
  const meta = ITEM_META[type]
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs" style={{ background: `${meta.color}22`, color: meta.color }}>
      <meta.Icon className="h-3.5 w-3.5" />
      {meta.name}
    </span>
  )
}
