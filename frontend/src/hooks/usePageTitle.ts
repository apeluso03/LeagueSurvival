import { useEffect } from 'react'

/** Sets the tab title. `null` leaves it alone (the page sets its own). */
export function usePageTitle(title: string | null) {
  useEffect(() => {
    if (title === null) return
    document.title = title ? `${title} · LoL Survival` : 'LoL Survival'
  }, [title])
}
