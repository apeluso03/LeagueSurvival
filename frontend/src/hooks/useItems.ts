import { api } from '../api/client'
import { ITEM_META } from '../lib/items'
import type { ItemType, ItemUse } from '../types'
import { useAction } from './queries'

/** Use one of a player's unused items of a type (the owner acts for everyone in the MVP). */
export function useOwnedItem(runId: number) {
  return useAction(async ({ playerId, type, body }: { playerId: number; type: ItemType; body: ItemUse }) => {
    const inv = await api.inventory(runId, playerId)
    const item = inv.find((i) => i.type === type && i.status === 'unused')
    if (!item) throw new Error(`No unused ${ITEM_META[type].name} for this player. Buy one in the Shop.`)
    return api.useItem(item.id, body)
  })
}

/** Buy an item, then (optionally) use it right away. */
export function useBuy(runId: number) {
  return useAction(({ playerId, type }: { playerId: number; type: ItemType }) => api.purchase(runId, playerId, type))
}
