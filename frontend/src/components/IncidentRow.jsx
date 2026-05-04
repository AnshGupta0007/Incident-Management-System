import { formatDistanceToNow } from 'date-fns'
import { useNavigate } from 'react-router-dom'
import { SeverityBadge, StatusBadge } from './SeverityBadge'

export function IncidentRow({ incident, highlight }) {
  const nav = useNavigate()
  return (
    <tr
      onClick={() => nav(`/incidents/${incident.id}`)}
      className={`cursor-pointer hover:bg-gray-800 transition-colors border-b border-gray-800
        ${highlight ? 'bg-gray-800 animate-pulse-once' : ''}`}
    >
      <td className="px-4 py-3 text-xs text-gray-500 font-mono">{incident.id.slice(0, 8)}…</td>
      <td className="px-4 py-3">
        <div className="text-sm font-semibold text-gray-100 truncate max-w-xs">{incident.title}</div>
        <div className="text-xs text-gray-500 flex items-center gap-2">
          <span>{incident.component_id}</span>
          {incident.mttr_minutes && (
            <span className="text-green-500">· MTTR {incident.mttr_minutes.toFixed(0)}m</span>
          )}
        </div>
      </td>
      <td className="px-4 py-3"><SeverityBadge severity={incident.severity} /></td>
      <td className="px-4 py-3"><StatusBadge status={incident.status} /></td>
      <td className="px-4 py-3 text-xs text-gray-400 text-right">
        {incident.signal_count} signals
      </td>
      <td className="px-4 py-3 text-xs text-gray-500 text-right">
        {formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}
      </td>
    </tr>
  )
}
