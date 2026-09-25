// Auth context (docs/PHASE_3_4_PLAN.md §1). Mirrors backend.tsx's provider shape.
// Off by default (`DEXTER_REQUIRE_AUTH=false` on the backend) — `me()` still resolves
// to the auto-created default Commander/My Business in that case, no token needed, so
// this provider never blocks the app; it only starts asking for a login once the
// backend itself has auth turned on.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError, setAuthToken, type BusinessInfo, type MeInfo } from './api'
import { useBackend } from './backend'

interface AuthState {
  loading: boolean
  requireAuth: boolean
  me: MeInfo | null
  needsLogin: boolean
  businesses: BusinessInfo[]
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, name: string, businessName: string, inviteCode?: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
  switchBusiness: (businessId: string) => Promise<void>
}

const AuthContext = createContext<AuthState>({
  loading: true, requireAuth: false, me: null, needsLogin: false, businesses: [],
  login: async () => {}, register: async () => {}, logout: () => {}, refresh: async () => {}, switchBusiness: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const { online } = useBackend()
  const [loading, setLoading] = useState(true)
  const [me, setMe] = useState<MeInfo | null>(null)
  const [requireAuth, setRequireAuth] = useState(false)
  const [needsLogin, setNeedsLogin] = useState(false)
  const [businesses, setBusinesses] = useState<BusinessInfo[]>([])

  const refresh = useCallback(async () => {
    try {
      const info = await api.me()
      setMe(info)
      setRequireAuth(info.require_auth)
      setNeedsLogin(false)
      // Only meaningful once signed in for real — off by default, and pointless to
      // fetch for the single always-there default business.
      if (info.require_auth) {
        api.businesses().then(setBusinesses).catch(() => setBusinesses([]))
      } else {
        setBusinesses([])
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setMe(null)
        setNeedsLogin(true)
      }
      // ApiOffline or other errors: leave whatever we had — the backend chip already
      // tells the user it's offline, no need for this provider to also error out.
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!online) { setLoading(false); return }
    refresh()
  }, [online, refresh])

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password)
    setAuthToken(res.token)
    await refresh()
  }, [refresh])

  const register = useCallback(async (email: string, password: string, name: string, businessName: string, inviteCode = '') => {
    const res = await api.register(email, password, name, businessName, inviteCode)
    setAuthToken(res.token)
    await refresh()
  }, [refresh])

  const logout = useCallback(() => {
    api.logout().catch(() => {})
    setAuthToken(null)
    setMe(null)
    setBusinesses([])
    setNeedsLogin(requireAuth)
  }, [requireAuth])

  const switchBusiness = useCallback(async (businessId: string) => {
    const info = await api.switchBusiness(businessId)
    setMe(info)
    setBusinesses((prev) => prev.map((b) => ({ ...b, current: b.id === businessId })))
  }, [])

  return (
    <AuthContext.Provider value={{ loading, requireAuth, me, needsLogin, businesses, login, register, logout, refresh, switchBusiness }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
