import { useState } from 'react'
import { api } from '../api/client'
import { useAction, useActiveRun } from '../hooks/queries'
import { ErrorText, Modal } from './ui'

/** Global challenge mode switch. Always visible in the header (SPEC 9.4). */
export function ModeToggle() {
  const { settings, run } = useActiveRun()
  const [confirming, setConfirming] = useState(false)
  const update = useAction(api.updateSettings)
  const on = settings.data?.challenge_mode ?? true
  if (!settings.data) return null

  const toggle = () => {
    if (on && run.data?.pending_game_id) setConfirming(true)
    else update.mutate({ challenge_mode: !on })
  }

  const turnOff = (voidPending: boolean) =>
    update.mutate({ challenge_mode: false, void_pending: voidPending }, { onSuccess: () => setConfirming(false) })

  return (
    <>
      <button
        onClick={toggle}
        disabled={!settings.data || update.isPending}
        aria-pressed={on}
        title={on ? 'Spins count for the challenge' : 'Spins are practice only'}
        className={`flex items-center gap-2 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide ring-1 transition ${
          on
            ? 'bg-emerald-500/15 text-emerald-300 ring-emerald-500/60 hover:bg-emerald-500/25'
            : 'bg-slate-700/40 text-slate-300 ring-slate-500 hover:bg-slate-700/60'
        }`}
      >
        <span className={`h-2.5 w-2.5 rounded-full ${on ? 'bg-emerald-400' : 'bg-slate-400'}`} />
        {on ? 'Challenge on' : 'Practice'}
      </button>
      {confirming && (
        <Modal title="A challenge game is pending" onClose={() => setConfirming(false)}>
          <p className="mb-4 text-sm text-slate-300">
            Turning challenge mode off stops results from changing the pool. What should happen to the pending game?
          </p>
          <ErrorText error={update.error} />
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <button className="btn-secondary" onClick={() => setConfirming(false)}>
              Cancel
            </button>
            <button className="btn-secondary" onClick={() => turnOff(false)}>
              Keep it pending
            </button>
            <button className="btn-danger" onClick={() => turnOff(true)}>
              Void the game
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}
