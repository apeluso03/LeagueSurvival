import { ITEM_META } from '../lib/items'
import type { ContractInfo } from '../types'
import { Modal } from './ui'

export function ContractReveal({ contract, playerName, onClose }: { contract: ContractInfo; playerName?: string; onClose: () => void }) {
  const Icon = ITEM_META.contract.Icon
  return (
    <Modal title={playerName ? `${playerName}'s contract` : 'Your contract'} onClose={onClose}>
      <div className="flex flex-col items-center gap-4 py-2 text-center">
        <div className="contract-reveal flex h-40 w-full max-w-xs flex-col items-center justify-center gap-2 rounded-3xl bg-gradient-to-b from-gold-700/40 to-gold-900/60 p-4 ring-1 ring-gold-400/50 ring-inset">
          <Icon className="h-8 w-8 text-gold-300" />
          <div className="font-display text-xl font-bold text-gold-100">{contract.description}</div>
          <div className="text-sm text-gold-300">Pays {contract.payout} gold</div>
        </div>
        <p className="text-sm text-slate-400">It counts in the next challenge game they play.</p>
        <button className="btn-primary" onClick={onClose}>
          Got it
        </button>
      </div>
    </Modal>
  )
}
