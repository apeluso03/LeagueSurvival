import type { ComponentType, SVGProps } from 'react'
import { BlacklistIcon, ChooseIcon, ContractIcon, RerollIcon, RoleIcon, ShieldIcon, SwapIcon } from '../components/icons'
import type { ItemType, Role } from '../types'

/** Display info for shop items. Prices and rules come from the backend. */
export const ITEM_META: Record<ItemType, { name: string; Icon: ComponentType<SVGProps<SVGSVGElement>>; color: string }> = {
  reroll: { name: 'Reroll', Icon: RerollIcon, color: '#2e9bff' },
  blacklist: { name: 'Blacklist', Icon: BlacklistIcon, color: '#e0434f' },
  swap: { name: 'Swap', Icon: SwapIcon, color: '#8b5cf6' },
  shield: { name: 'Shield', Icon: ShieldIcon, color: '#4fae6b' },
  choose: { name: 'Choose a Champ', Icon: ChooseIcon, color: '#e3c04d' },
  contract: { name: 'Contract', Icon: ContractIcon, color: '#e8823a' },
  role: { name: 'Role Select', Icon: RoleIcon, color: '#19d3e6' },
}

export const ITEM_ORDER: ItemType[] = ['reroll', 'blacklist', 'role', 'swap', 'shield', 'choose', 'contract']

/** Role Select roles, as the game names them, with their short names. */
export const SELECT_ROLES: { id: Role; name: string; hint: string }[] = [
  { id: 'TOP', name: 'Top', hint: 'Top lane' },
  { id: 'JUNGLE', name: 'Jungle', hint: 'Jungle' },
  { id: 'MIDDLE', name: 'Mid', hint: 'Mid lane' },
  { id: 'BOTTOM', name: 'Bot', hint: 'Bot lane (ADC)' },
  { id: 'UTILITY', name: 'Support', hint: 'Support' },
]
export const roleName = (r: Role | string | null | undefined) => SELECT_ROLES.find((x) => x.id === r)?.name ?? r ?? ''

export const formatGold = (n: number) => n.toLocaleString()

/** "+104" / "−250" for ledger rows. */
export const signedGold = (n: number) => `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n).toLocaleString()}`
