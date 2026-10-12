import type { ComponentType, SVGProps } from 'react'
import { BlacklistIcon, ChooseIcon, ContractIcon, RerollIcon, ShieldIcon, SwapIcon } from '../components/icons'
import type { ItemType } from '../types'

/** Display info for shop items. Prices and rules come from the backend. */
export const ITEM_META: Record<ItemType, { name: string; Icon: ComponentType<SVGProps<SVGSVGElement>>; color: string }> = {
  reroll: { name: 'Reroll', Icon: RerollIcon, color: '#0ac8b9' },
  blacklist: { name: 'Blacklist', Icon: BlacklistIcon, color: '#e0434f' },
  swap: { name: 'Swap', Icon: SwapIcon, color: '#8b5cf6' },
  shield: { name: 'Shield', Icon: ShieldIcon, color: '#4fae6b' },
  choose: { name: 'Choose a Champ', Icon: ChooseIcon, color: '#e3c04d' },
  contract: { name: 'Contract', Icon: ContractIcon, color: '#e8823a' },
}

export const ITEM_ORDER: ItemType[] = ['reroll', 'blacklist', 'swap', 'shield', 'choose', 'contract']

export const formatGold = (n: number) => n.toLocaleString()

/** "+104" / "−250" for ledger rows. */
export const signedGold = (n: number) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n).toLocaleString()}`
