import { useState } from 'react'
import { api } from '../api/client'
import { useAction, useActiveRun } from '../hooks/queries'
import { useAccess } from '../hooks/useAuth'
import { ErrorText, Modal } from './ui'

/** Global challenge mode switch. Always visible in the header (SPEC 9.4). */
export function ModeToggle() {
  const { settings, run } = useActiveRun()
  const [confirming, setConfirming] = useState(false)
  const update = useAction(api.updateSettings)
  const { isAdmin } = useAccess()
  const on = settings.data?.challenge_mode ?? true
  if (!settings.data) return null

  if (!isAdmin) {
    return (
      <span
        className="broadcast-tag py-1"
        title={on ? 'Games count for the challenge. Only the owner can switch this.' : 'Practice only. Only the owner can switch this.'}
        style={{ ['--tag' as string]: on ? '#e5283c' : '#454e5e' }}
      >
        {on && <span className="live-dot" />}
        {on ? 'Live · Challenge' : 'Practice'}
      </span>
    )
  }

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
        className="broadcast-tag py-1 transition hover:brightness-125"
        style={{ ['--tag' as string]: on ? '#e5283c' : '#454e5e' }}
      >
        {on && <span className="live-dot" />}
        {on ? 'Live · Challenge' : 'Practice'}
      </button>
      {confirming && (
        <Modal title="There's a game going" onClose={() => setConfirming(false)}>
          <p className="mb-4 text-sm text-slate-300">
            With challenge mode off, results won't touch the pool. What do you want to do with the current game?
          </p>
          <ErrorText error={update.error} />
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <button className="btn-secondary" onClick={() => setConfirming(false)}>
              Cancel
            </button>
            <button className="btn-secondary" onClick={() => turnOff(false)}>
              Keep it
            </button>
            <button className="btn-danger" onClick={() => turnOff(true)}>
              Throw it out
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}
