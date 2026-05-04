import { useEffect, useState } from 'react'
import { getHealth } from '../services/api'

export function HealthBar() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    const fetch = () => getHealth().then(setHealth).catch(() => setHealth(null))
    fetch()
    const t = setInterval(fetch, 15000)
    return () => clearInterval(t)
  }, [])

  if (!health) return null

  const services = health.services || {}
  return (
    <div className="flex items-center gap-4 text-xs">
      {Object.entries(services).map(([name, info]) => (
        <div key={name} className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full ${info.status === 'ok' ? 'bg-green-400' : 'bg-red-400'}`} />
          <span className="text-gray-400 uppercase">{name}</span>
          {name === 'redis' && info.stream_backlog != null && (
            <span className="text-gray-600">({info.stream_backlog} queued)</span>
          )}
        </div>
      ))}
    </div>
  )
}
