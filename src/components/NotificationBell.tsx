// Bell icon in the topbar: opens a dropdown (desktop) / sheet (mobile)
// listing pending approval gates, with inline approve/reject actions.
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Gate } from '../lib/api'
import { useBackend } from '../lib/backend'
import { useToast } from '../lib/toast'

function relTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diffSec = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (diffSec < 60) return 'just now'
  const diffMin = Math.round(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.round(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.round(diffHr / 24)
  return `${diffDay}d ago`
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const { online, gates, refreshGates } = useBackend()
  const { push } = useToast()

  useEffect(() => {
    if (!open) return
    function onPointerDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const approve = useCallback(async (gate: Gate) => {
    setBusyId(gate.task_id)
    try {
      await api.approveGate(gate.task_id)
      await refreshGates()
      push({ kind: 'good', title: 'Gate approved', body: gate.task_title || gate.task_id })
    } catch {
      push({ kind: 'warn', title: 'Approve failed', body: 'Could not reach the backend — try again.' })
    } finally {
      setBusyId(null)
    }
  }, [refreshGates, push])

  const reject = useCallback(async (gate: Gate) => {
    setBusyId(gate.task_id)
    try {
      await api.rejectGate(gate.task_id)
      await refreshGates()
      push({ kind: 'info', title: 'Gate rejected', body: gate.task_title || gate.task_id })
    } catch {
      push({ kind: 'warn', title: 'Reject failed', body: 'Could not reach the backend — try again.' })
    } finally {
      setBusyId(null)
    }
  }, [refreshGates, push])

  // `gates` can lag one snapshot behind `online` (backend.tsx doesn't clear
  // it on going offline), so gate the badge on both to avoid flashing a
  // stale count next to an "unavailable" panel.
  const count = online ? gates.length : 0

  return (
    <div className="notif-wrap" ref={wrapRef}>
      <button
        className={`iconbtn${open ? ' on' : ''}`}
        aria-label="Notifications"
        aria-expanded={open}
        aria-haspopup="dialog"
        title="Approval gates"
        onClick={() => setOpen((v) => !v)}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {count > 0 && <span className="count">{count > 9 ? '9+' : count}</span>}
      </button>

      {open && (
        <div className="notif-panel" role="dialog" aria-label="Approval Gates">
          <div className="notif-head">
            <span className="label">Approval Gates</span>
            <span className="notif-head-count">{count}</span>
          </div>

          <div className="notif-list">
            {!online && (
              <div className="notif-empty dim">Backend offline — gates unavailable.</div>
            )}

            {online && count === 0 && (
              <div className="notif-empty">
                <span className="notif-empty-glyph">◈</span>
                No gates pending. The Shadow runs clean.
              </div>
            )}

            {online && gates.map((g) => (
              <div className="notif-item" key={g.task_id}>
                <div className="notif-item-top">
                  <span className="notif-item-title">{g.task_title || g.task_id}</span>
                  <span className="notif-item-time">{relTime(g.created_at)}</span>
                </div>
                {g.reason && <div className="notif-item-reason">{g.reason}</div>}
                <div className="notif-item-actions">
                  <button
                    className="notif-btn primary"
                    disabled={busyId === g.task_id}
                    onClick={() => approve(g)}
                  >
                    Approve
                  </button>
                  <button
                    className="notif-btn ghost"
                    disabled={busyId === g.task_id}
                    onClick={() => reject(g)}
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
