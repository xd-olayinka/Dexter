// Global backend state: polls health + gates + spend while online,
// backs off while offline. Everything downstream reads useBackend().
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type SystemStatus, type Gate, type BudgetSnapshot } from './api'

interface BackendState {
  online: boolean
  checked: boolean
  status: SystemStatus | null
  gates: Gate[]
  budget: BudgetSnapshot | null
  refreshStatus: () => Promise<void>
  refreshGates: () => Promise<void>
}

const BackendContext = createContext<BackendState>({
  online: false,
  checked: false,
  status: null,
  gates: [],
  budget: null,
  refreshStatus: async () => {},
  refreshGates: async () => {},
})

const STATUS_MS = 15000
const GATES_MS = 6000
const OFFLINE_RETRY_MS = 20000

export function BackendProvider({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState(false)
  const [checked, setChecked] = useState(false)
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [gates, setGates] = useState<Gate[]>([])
  const [budget, setBudget] = useState<BudgetSnapshot | null>(null)
  const onlineRef = useRef(online)
  onlineRef.current = online

  const refreshStatus = useCallback(async () => {
    try {
      const s = await api.status()
      setStatus(s)
      setOnline(true)
    } catch {
      setOnline(false)
      setStatus(null)
    } finally {
      setChecked(true)
    }
  }, [])

  const refreshGates = useCallback(async () => {
    if (!onlineRef.current) return
    try {
      const [g, b] = await Promise.all([api.gates(), api.budget()])
      setGates(g)
      setBudget(b)
    } catch {
      /* transient — status poll owns the online flag */
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    async function loop() {
      await refreshStatus()
      if (cancelled) return
      timer = setTimeout(loop, onlineRef.current ? STATUS_MS : OFFLINE_RETRY_MS)
    }
    loop()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [refreshStatus])

  useEffect(() => {
    if (!online) return
    refreshGates()
    const t = setInterval(refreshGates, GATES_MS)
    return () => clearInterval(t)
  }, [online, refreshGates])

  return (
    <BackendContext.Provider value={{ online, checked, status, gates, budget, refreshStatus, refreshGates }}>
      {children}
    </BackendContext.Provider>
  )
}

export function useBackend() {
  return useContext(BackendContext)
}
