import { useState } from 'react'
import type { ActionResponse, MilestoneView } from './api'

/** Runs one backend action: tracks busy/error and hands the fresh on-chain view up. */
export function useAction(onView: (view: MilestoneView) => void) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<ActionResponse>): Promise<ActionResponse | null> {
    setBusy(true)
    setError(null)
    try {
      const response = await action()
      onView(response.view)
      return response
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return null
    } finally {
      setBusy(false)
    }
  }

  return { busy, error, run }
}
