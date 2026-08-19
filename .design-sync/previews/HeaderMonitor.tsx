import { HeaderMonitor } from 'adaptive-action-copilot-ui'
import { TELEMETRY, TELEMETRY_BUSY } from './_fixtures'

/* The always-visible LLM monitor. It reads the backend's own ledger rather than
   a SaaS round trip, so it has three states worth seeing: connecting, live, and
   backend-unreachable. */

export function Live() {
  return <HeaderMonitor data={TELEMETRY} offline={false} />
}

export function InFlight() {
  return <HeaderMonitor data={TELEMETRY_BUSY} offline={false} />
}

export function Connecting() {
  return <HeaderMonitor data={null} offline={false} />
}

export function BackendOffline() {
  return <HeaderMonitor data={null} offline />
}
