import { useEffect, useRef, useCallback } from 'react'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`

export function useWebSocket(onMessage) {
  const ws = useRef(null)
  const reconnectTimer = useRef(null)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return

    try {
      ws.current = new WebSocket(WS_URL)

      ws.current.onopen = () => {
        clearTimeout(reconnectTimer.current)
      }

      ws.current.onmessage = e => {
        try {
          const data = JSON.parse(e.data)
          onMessageRef.current(data)
        } catch {
          // pong or malformed frame — ignore
        }
      }

      ws.current.onclose = () => {
        reconnectTimer.current = setTimeout(connect, 3000)
      }

      ws.current.onerror = () => {
        ws.current?.close()
      }
    } catch {
      reconnectTimer.current = setTimeout(connect, 3000)
    }
  }, [])

  useEffect(() => {
    connect()
    const heartbeat = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send('ping')
      }
    }, 25000)

    return () => {
      clearInterval(heartbeat)
      clearTimeout(reconnectTimer.current)
      ws.current?.close()
    }
  }, [connect])
}
