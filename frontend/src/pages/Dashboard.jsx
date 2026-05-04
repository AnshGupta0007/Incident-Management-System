import { useCallback, useEffect, useState } from 'react'
import { getIncidents, simulateBurst, simulateDbFailure, resetSimulation, getSimStatus, api } from '../services/api'
import { useWebSocket } from '../hooks/useWebSocket'
import { IncidentRow } from '../components/IncidentRow'
import { MetricsChart } from '../components/MetricsChart'

const SEVERITY_ORDER = { P0: 0, P1: 1, P2: 2, P3: 3, P4: 4 }

export default function Dashboard() {
  const [incidents, setIncidents] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState({ status: '', severity: '', page: 1 })
  const [simStatus, setSimStatus] = useState(null)
  const [summary, setSummary] = useState(null)
  const [highlightIds, setHighlightIds] = useState(new Set())
  const [simMsg, setSimMsg] = useState('')

  const fetchIncidents = useCallback(async () => {
    try {
      const params = {}
      if (filter.status) params.status = filter.status
      if (filter.severity) params.severity = filter.severity
      params.page = filter.page
      params.page_size = 20
      const data = await getIncidents(params)
      const sorted = [...data.items].sort((a, b) =>
        (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
      )
      setIncidents(sorted)
      setTotal(data.total)
    } catch {
      // ignore transient errors
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => { fetchIncidents() }, [fetchIncidents])

  useEffect(() => {
    const fetchSim = () => getSimStatus().then(setSimStatus).catch(() => {})
    const fetchSummary = () => api.get('/metrics/summary').then(r => setSummary(r.data)).catch(() => {})
    fetchSim(); fetchSummary()
    const t1 = setInterval(fetchSim, 5000)
    const t2 = setInterval(fetchSummary, 10000)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [])

  const handleWsMessage = useCallback(msg => {
    if (msg.type === 'signal_processed' || msg.type === 'status_changed') {
      fetchIncidents()
      if (msg.work_item_id) {
        setHighlightIds(s => new Set([...s, msg.work_item_id]))
        setTimeout(() => setHighlightIds(s => { const n = new Set(s); n.delete(msg.work_item_id); return n }), 2000)
      }
    }
  }, [fetchIncidents])

  useWebSocket(handleWsMessage)

  const runSim = async (fn, label) => {
    setSimMsg(`Running: ${label}…`)
    try { const r = await fn(); setSimMsg(r.message || `${label} done`) }
    catch { setSimMsg('Simulation failed') }
    setTimeout(() => setSimMsg(''), 5000)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Live Incident Feed</h1>
          <p className="text-gray-500 text-sm">{total} total incidents</p>
        </div>
        <div className="flex items-center gap-2">
          {simStatus?.stream_backlog > 0 && (
            <span className="text-yellow-400 text-xs animate-pulse">
              {simStatus.stream_backlog} signals queued
            </span>
          )}
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {['P0','P1','P2','P3','P4'].map(sev => {
            const count = summary.active_by_severity?.[sev] ?? 0
            const colors = { P0:'text-red-400 border-red-800', P1:'text-orange-400 border-orange-800', P2:'text-yellow-400 border-yellow-800', P3:'text-green-400 border-green-800', P4:'text-blue-400 border-blue-800' }
            return (
              <div key={sev} className={`card border text-center ${colors[sev]}`}>
                <div className="text-xs text-gray-500 uppercase">{sev} Active</div>
                <div className="text-2xl font-bold mt-1">{count}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* Timeseries Chart */}
      <MetricsChart />

      {/* Simulation Controls */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-gray-300 uppercase tracking-wide">
            Failure Simulation Engine
          </h2>
          {simStatus && (
            <div className="flex gap-2 text-xs">
              {simStatus.db_failure_active && <span className="text-red-400 animate-pulse">DB FAILURE ACTIVE</span>}
              {simStatus.latency_spike_ms && <span className="text-orange-400 animate-pulse">LATENCY +{simStatus.latency_spike_ms}ms</span>}
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => runSim(simulateBurst, 'Burst (200 signals)')} className="btn-danger text-xs">
            🔥 Simulate Burst (200 signals)
          </button>
          <button onClick={() => runSim(() => simulateDbFailure(20), 'DB Failure')} className="btn text-xs bg-orange-900 hover:bg-orange-800 text-orange-300">
            💥 DB Failure (20s)
          </button>
          <button onClick={() => runSim(resetSimulation, 'Reset')} className="btn-ghost text-xs">
            ✅ Reset Simulations
          </button>
        </div>
        {simMsg && <p className="text-gray-400 text-xs mt-2">{simMsg}</p>}
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <select
          value={filter.status}
          onChange={e => setFilter(f => ({ ...f, status: e.target.value, page: 1 }))}
          className="input w-40"
        >
          <option value="">All Statuses</option>
          <option value="OPEN">OPEN</option>
          <option value="INVESTIGATING">INVESTIGATING</option>
          <option value="RESOLVED">RESOLVED</option>
          <option value="CLOSED">CLOSED</option>
        </select>
        <select
          value={filter.severity}
          onChange={e => setFilter(f => ({ ...f, severity: e.target.value, page: 1 }))}
          className="input w-36"
        >
          <option value="">All Severities</option>
          {['P0','P1','P2','P3','P4'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button onClick={fetchIncidents} className="btn-ghost">Refresh</button>
      </div>

      {/* Incident Table */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-800 text-gray-400 text-xs uppercase tracking-wide">
              <th className="px-4 py-3 text-left">ID</th>
              <th className="px-4 py-3 text-left">Incident</th>
              <th className="px-4 py-3 text-left">Severity</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-right">Signals</th>
              <th className="px-4 py-3 text-right">Age</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">Loading…</td></tr>
            ) : incidents.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                No incidents found. Use the simulation engine above to generate some.
              </td></tr>
            ) : incidents.map(i => (
              <IncidentRow key={i.id} incident={i} highlight={highlightIds.has(i.id)} />
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        {total > 20 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-800">
            <span className="text-xs text-gray-500">
              Page {filter.page} of {Math.ceil(total / 20)}
            </span>
            <div className="flex gap-2">
              <button
                disabled={filter.page === 1}
                onClick={() => setFilter(f => ({ ...f, page: f.page - 1 }))}
                className="btn-ghost text-xs"
              >← Prev</button>
              <button
                disabled={filter.page >= Math.ceil(total / 20)}
                onClick={() => setFilter(f => ({ ...f, page: f.page + 1 }))}
                className="btn-ghost text-xs"
              >Next →</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
