import { formatGold } from '../lib/items'
import { CoinIcon } from './icons'

export function GoldBadge({ amount, size = 'sm' }: { amount: number; size?: 'sm' | 'lg' }) {
  const big = size === 'lg'
  return (
    <span
      className={`inline-flex items-center gap-1 font-bold tabular-nums ${big ? 'text-3xl text-gold-200' : 'text-sm text-gold-300'} ${
        amount < 0 ? 'text-red-300' : ''
      }`}
      title={`${formatGold(amount)} gold`}
    >
      <CoinIcon className={big ? 'h-7 w-7' : 'h-4 w-4'} />
      {formatGold(amount)}
    </span>
  )
}
