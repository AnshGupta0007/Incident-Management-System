export function SeverityBadge({ severity }) {
  const cls = {
    P0: 'badge-p0',
    P1: 'badge-p1',
    P2: 'badge-p2',
    P3: 'badge-p3',
    P4: 'badge-p4',
  }[severity] || 'badge-p4'

  return <span className={cls}>{severity}</span>
}

export function StatusBadge({ status }) {
  const map = {
    OPEN:          'bg-red-900 text-red-300 border-red-700',
    INVESTIGATING: 'bg-yellow-900 text-yellow-300 border-yellow-700',
    RESOLVED:      'bg-green-900 text-green-300 border-green-700',
    CLOSED:        'bg-gray-700 text-gray-400 border-gray-600',
  }
  const cls = map[status] || 'bg-gray-700 text-gray-400 border-gray-600'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold border ${cls}`}>
      {status}
    </span>
  )
}
