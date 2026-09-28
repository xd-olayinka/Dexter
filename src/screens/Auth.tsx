// Login/register screen (docs/PHASE_3_4_PLAN.md §1). Only ever shown once the backend
// has DEXTER_REQUIRE_AUTH=true and this browser has no valid session — see App.tsx's
// gating and lib/auth.tsx's `needsLogin`.
import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { ApiError } from '../lib/api'

export default function Auth() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [businessName, setBusinessName] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      if (mode === 'login') await login(email, password)
      else await register(email, password, name, businessName || 'My Business', inviteCode.trim())
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reach the backend')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="content" style={{ maxWidth: 380, margin: '10vh auto 0' }}>
      <div className="eyebrow">D.E.X.T.E.R + A.N.T.H.O.N.Y</div>
      <h1 className="bigtitle" style={{ fontSize: 28 }}>{mode === 'login' ? 'Welcome back, Commander' : 'Stand up a new business'}</h1>
      <div className="card">
        {mode === 'register' && (
          <div className="set-field">
            <label className="label set-label">Your name</label>
            <input className="set-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Commander" />
          </div>
        )}
        <div className="set-field">
          <label className="label set-label">Email</label>
          <input className="set-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
        </div>
        <div className="set-field">
          <label className="label set-label">Password</label>
          <input
            className="set-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
          />
        </div>
        {mode === 'register' && (
          <div className="set-field">
            <label className="label set-label">Business name</label>
            <input className="set-input" value={businessName} onChange={(e) => setBusinessName(e.target.value)} placeholder="My Business" />
          </div>
        )}
        {mode === 'register' && (
          <div className="set-field">
            <label className="label set-label">Invite code (if you were invited)</label>
            <input className="set-input" value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} placeholder="Leave blank to start your own business" />
          </div>
        )}
        {error && <p className="subnote" style={{ color: 'var(--warn, #C7361F)' }}>{error}</p>}
        <button className="set-btn wide" disabled={busy || !email || !password} onClick={submit} style={{ marginTop: 8 }}>
          {busy ? 'Working…' : mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
        <button
          className="set-btn wide" style={{ marginTop: 8, background: 'transparent', color: 'var(--jet)', border: '1px solid var(--line)' }}
          onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}
        >
          {mode === 'login' ? "Don't have an account? Register" : 'Already have an account? Sign in'}
        </button>
      </div>
    </div>
  )
}
