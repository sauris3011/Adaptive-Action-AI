import { useEffect, useRef, useState } from 'react'
import { api, type TelemetrySummary } from './api'

const POLL_MS = 1500

/* Polling rather than SSE, deliberately.
   The header monitor is always visible, so its failure mode is the one the room
   sees. A poll that misses a tick self-corrects on the next one; a dropped
   EventSource needs reconnect logic that is not worth writing at this scale. */
export function useTelemetry() {
  const [data, setData] = useState<TelemetrySummary | null>(null)
  const [offline, setOffline] = useState(false)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    let timer: number

    const tick = async () => {
      try {
        const summary = await api.telemetry()
        if (!mounted.current) return
        setData(summary)
        setOffline(false)
      } catch {
        if (mounted.current) setOffline(true)
      } finally {
        if (mounted.current) timer = window.setTimeout(tick, POLL_MS)
      }
    }

    void tick()
    return () => {
      mounted.current = false
      window.clearTimeout(timer)
    }
  }, [])

  return { data, offline }
}
