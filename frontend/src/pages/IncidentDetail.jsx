import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { formatDistanceToNow, format } from 'date-fns'
import { getIncident, getSignals, updateStatus, getReplay } from '../services/api'
import { SeverityBadge, StatusBadge } from '../components/SeverityBadge'
import { RCAForm } from '../components/RCAForm'
import { useWebSocket } from '../hooks/useWebSocket'

const TRANSITIONS = {
  OPEN: ['INVESTIGATING'],
  INVESTIGATING: ['RESOLVED', 'OPEN'],
  RESOLVED: ['CLOSED', 'INVESTIGATING'],
  CLOSED: ['OPEN'],
}

export default function IncidentDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [incident, setIncident] = useState(null)
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('signals')
  const [transitioning, setTransitioning] = useState(false)
  const [error, setError] = useState('')
  const [replay, setReplay] = useState(null)

  const fetchAll = useCallback(async () => {
    try {
      const [inc, sigs] = await Promise.all([
        getIncident(id),
        getSignals(id, 100),
      ])
      setIncident(inc)
      setSignals(sigs)
    } catch {
      setError('Incident not found')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { fetchAll() }, [fetchAll])

  useWebSocket(useCallback(msg => {
    if ((msg.type === 'status_changed' || msg.type === 'rca_submitted') && msg.work_item_id === id) {
      fetchAll()
    }
  }, [id, fetchAll]))

  const transition = async status => {
    setTransitioning(true)
    setError('')
    try {
      await updateStatus(id, status)
      await fetchAll()
    } catch (err) {
      setError(err.response?.data?.detail || 'Transition failed')
    } finally {
      setTransitioning(false)
    }
  }

  const loadReplay = async () => {
    const r = await getReplay(id)
    setReplay(r)
    setTab('replay')
  }

  if (loading) return <div className="text-gray-500 p-8">Loading…</div>
  if (!incident) return <div className="text-red-400 p-8">{error || 'Not found'}</div>

  const allowedTransitions = TRANSITIONS[incident.status] || []

  return (
    <div className="space-y-6">
      {/* Back */}
      <button onClick={() => nav('/')} className="text-gray-500 text-sm hover:text-gray-300">
        ← Back to dashboard
      </button>

      {/* Header */}
      <div className="card">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <SeverityBadge severity={incident.severity} />
              <StatusBadge status={incident.status} />
              {incident.mttr_minutes && (
                <span className="text-xs text-green-400">MTTR: {incident.mttr_minutes.toFixed(1)}m</span>
              )}
            </div>
            <h1 className="text-xl font-bold text-white truncate">{incident.title}</h1>
            <p className="text-gray-500 text-sm mt-1">{incident.component_id} · {incident.component_type}</p>
          </div>
          <div className="text-right text-xs text-gray-500 shrink-0">
            <div>{incident.signal_count} signals</div>
            <div>{formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}</div>
          </div>
        </div>

        {/* State Transitions */}
        {allowedTransitions.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="text-xs text-gray-500 self-center">Transition:</span>
            {allowedTransitions.map(s => (
              <button
                key={s}
                onClick={() => transition(s)}
                disabled={transitioning}
                className={`btn text-xs ${
                  s === 'CLOSED' ? 'bg-gray-700 hover:bg-gray-600 text-gray-300' :
                  s === 'RESOLVED' ? 'bg-green-900 hover:bg-green-800 text-green-300' :
                  'bg-yellow-900 hover:bg-yellow-800 text-yellow-300'
                }`}
              >
                → {s}
              </button>
            ))}
          </div>
        )}

        {error && (
          <div className="mt-3 bg-red-950 border border-red-700 rounded p-3 text-red-300 text-sm">
            {error}
          </div>
        )}
      </div>

      {/* Metadata */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          ['Created', format(new Date(incident.created_at), 'MMM d, HH:mm:ss')],
          ['Updated', format(new Date(incident.updated_at), 'MMM d, HH:mm:ss')],
          ['Resolved', incident.resolved_at ? format(new Date(incident.resolved_at), 'MMM d, HH:mm:ss') : '—'],
          ['MTTR', incident.mttr_minutes ? `${incident.mttr_minutes.toFixed(1)} min` : '—'],
        ].map(([k, v]) => (
          <div key={k} className="card text-center">
            <div className="text-xs text-gray-500 uppercase">{k}</div>
            <div className="text-sm font-semibold mt-1">{v}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-800 flex gap-1">
        {['signals', 'rca', 'replay'].map(t => (
          <button
            key={t}
            onClick={t === 'replay' ? loadReplay : () => setTab(t)}
            className={`px-4 py-2 text-sm font-semibold transition-colors capitalize
              ${tab === t ? 'text-white border-b-2 border-blue-500' : 'text-gray-500 hover:text-gray-300'}`}
          >
            {t === 'signals' ? `Signals (${signals.length})` : t.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Tab: Signals */}
      {tab === 'signals' && (
        <div className="space-y-2">
          {signals.length === 0 ? (
            <p className="text-gray-500 text-sm">No signals yet.</p>
          ) : signals.map((s, i) => (
            <div key={i} className="card text-xs font-mono">
              <div className="flex items-center gap-2 mb-1">
                <SeverityBadge severity={s.severity} />
                <span className="text-gray-500">{s.signal_type}</span>
                <span className="text-gray-600 ml-auto">
                  {s.timestamp ? format(new Date(s.timestamp), 'HH:mm:ss.SSS') : ''}
                </span>
              </div>
              <p className="text-gray-300">{s.message}</p>
              {s.source_host && <p className="text-gray-600 mt-1">host: {s.source_host}</p>}
            </div>
          ))}
        </div>
      )}

      {/* Tab: RCA */}
      {tab === 'rca' && (
        <div>
          {incident.rca ? (
            <div className="card space-y-4">
              <h3 className="font-bold text-white">Root Cause Analysis</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-xs text-gray-500 uppercase mb-1">Category</div>
                  <div className="text-yellow-300 font-semibold">{incident.rca.root_cause_category}</div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 uppercase mb-1">MTTR</div>
                  <div className="text-green-300 font-semibold">
                    {incident.rca.mttr_minutes?.toFixed(1)} minutes
                  </div>
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500 uppercase mb-1">Root Cause</div>
                <p className="text-gray-300 text-sm">{incident.rca.root_cause_detail}</p>
              </div>
              <div>
                <div className="text-xs text-gray-500 uppercase mb-1">Fix Applied</div>
                <p className="text-gray-300 text-sm">{incident.rca.fix_applied}</p>
              </div>
              <div>
                <div className="text-xs text-gray-500 uppercase mb-1">Prevention Steps</div>
                <p className="text-gray-300 text-sm">{incident.rca.prevention_steps}</p>
              </div>
              {incident.rca.impact_summary && (
                <div>
                  <div className="text-xs text-gray-500 uppercase mb-1">Impact</div>
                  <p className="text-gray-300 text-sm">{incident.rca.impact_summary}</p>
                </div>
              )}
              <div className="text-xs text-gray-600">
                Submitted by {incident.rca.created_by || 'anonymous'} ·{' '}
                {format(new Date(incident.rca.created_at), 'MMM d, HH:mm')}
              </div>
              {incident.status !== 'CLOSED' && (
                <div className="bg-yellow-950 border border-yellow-700 rounded p-3 text-yellow-300 text-xs">
                  RCA submitted. You can now transition to CLOSED.
                </div>
              )}
            </div>
          ) : (
            <div className="card">
              <h3 className="font-bold text-white mb-4">Submit Root Cause Analysis</h3>
              {incident.status === 'CLOSED' ? (
                <p className="text-gray-500 text-sm">Incident is closed.</p>
              ) : (
                <RCAForm
                  workItemId={id}
                  createdAt={incident.created_at}
                  onSuccess={fetchAll}
                />
              )}
            </div>
          )}
        </div>
      )}

      {/* Tab: Replay */}
      {tab === 'replay' && replay && (
        <div className="space-y-2">
          <div className="text-xs text-gray-500 mb-3">
            {replay.total_signals} signals — chronological replay
          </div>
          {replay.timeline.map((s, i) => (
            <div key={i} className="flex gap-3 text-xs">
              <span className="text-gray-600 shrink-0 font-mono">
                {s.timestamp ? format(new Date(s.timestamp), 'HH:mm:ss.SSS') : ''}
              </span>
              <SeverityBadge severity={s.severity} />
              <span className="text-gray-300">{s.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
