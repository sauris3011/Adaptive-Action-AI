import { AppHeader } from 'adaptive-action-copilot-ui'
import { TELEMETRY, TELEMETRY_BUSY } from './_fixtures'

/* The app chrome: brand mark, primary nav, the LLM monitor, theme and settings.
   Renders inside the MemoryRouter the preview provider supplies — NavLink needs
   a router context, and the active-route styling is part of what this shows. */

export function Default() {
  return <AppHeader telemetry={TELEMETRY} offline={false} onOpenSettings={() => {}} />
}

export function InFlight() {
  return <AppHeader telemetry={TELEMETRY_BUSY} offline={false} onOpenSettings={() => {}} />
}

export function BackendOffline() {
  return <AppHeader telemetry={null} offline onOpenSettings={() => {}} />
}
