// Pure effect: watches pending gates and announces newly-appeared ones
// as sticky toasts, anywhere in the app. Renders nothing.
import { useEffect, useRef } from 'react'
import { api } from '../lib/api'
import { useBackend } from '../lib/backend'
import { useToast } from '../lib/toast'

export default function GateWatcher() {
  const { gates, refreshGates } = useBackend()
  const { push } = useToast()

  // The very first render's `gates` reference is the context's pre-fetch
  // default ([]), not real poll data — comparing against it (rather than
  // just "first effect run") keeps us from priming on that default and
  // then treating the *actual* first fetch as a batch of "new" gates,
  // which would toast-storm every pre-existing gate on page load.
  const initialGates = useRef(gates)
  const primed = useRef(false)
  const announced = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!primed.current && gates === initialGates.current) return

    const currentIds = new Set(gates.map((g) => g.task_id))

    if (!primed.current) {
      announced.current = currentIds
      primed.current = true
      return
    }

    for (const gate of gates) {
      if (announced.current.has(gate.task_id)) continue
      announced.current.add(gate.task_id)

      push({
        kind: 'gate',
        sticky: true,
        title: gate.task_title || 'Approval required',
        body: gate.reason,
        actions: [
          {
            label: 'Approve',
            kind: 'primary',
            onClick: async () => {
              try {
                await api.approveGate(gate.task_id)
                await refreshGates()
              } catch {
                push({ kind: 'warn', title: 'Approve failed', body: 'Could not reach the backend — try again.' })
              }
            },
          },
          {
            label: 'Reject',
            onClick: async () => {
              try {
                await api.rejectGate(gate.task_id)
                await refreshGates()
              } catch {
                push({ kind: 'warn', title: 'Reject failed', body: 'Could not reach the backend — try again.' })
              }
            },
          },
        ],
      })
    }

    for (const id of announced.current) {
      if (!currentIds.has(id)) announced.current.delete(id)
    }
  }, [gates, push, refreshGates])

  return null
}
