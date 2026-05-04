import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts'
import { format } from 'date-fns'
import { api } from '../services/api'

const SEVERITY_COLORS = {
  P0: '#ef4444',
  P1: '#f97316',
  P2: '#eab308',
  P3: '#22c55e',
  P4: '#3b82f6',
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-900 border border-gray-700 rounded p-3 text-xs">
      <p className="text-gray-400 mb-2">{label}</p>
      {payload.map(p => (
        <div key={p.name} className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-gray-300">{p.name}: {p.value}</span>
        </div>
      ))}
    </div>
  )
}

export function MetricsChart() {
  const [data, setData] = useState([])
  const [hours, setHours] = useState(24)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    api.get(`/metrics/timeseries?hours=${hours}`)
      .then(r => {
        const formatted = r.data.map(d => ({
          ...d,
          time: format(new Date(d.time), 'HH:mm'),
        }))
        setData(formatted)
      })
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [hours])

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-bold text-gray-300 uppercase tracking-wide">
          Signal Volume (per hour)
        </h2>
        <select
          value={hours}
          onChange={e => setHours(Number(e.target.value))}
          className="input w-28 text-xs"
        >
          <option value={6}>Last 6h</option>
          <option value={24}>Last 24h</option>
          <option value={48}>Last 48h</option>
          <option value={168}>Last 7d</option>
        </select>
      </div>

      {loading ? (
        <div className="h-40 flex items-center justify-center text-gray-600 text-sm">
          Loading…
        </div>
      ) : data.length === 0 ? (
        <div className="h-40 flex items-center justify-center text-gray-600 text-sm">
          No signal data yet — run the sample generator to populate
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 11, color: '#9ca3af', paddingTop: 8 }}
            />
            {['P0', 'P1', 'P2', 'P3', 'P4'].map(s => (
              <Bar key={s} dataKey={s} stackId="a" fill={SEVERITY_COLORS[s]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
