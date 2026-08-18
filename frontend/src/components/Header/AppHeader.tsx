import { Settings } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import type { TelemetrySummary } from '../../lib/api'
import { HeaderMonitor } from './HeaderMonitor'
import { ThemeToggle } from './ThemeToggle'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-2.5 py-1.5 text-sm transition-colors ${
    isActive ? 'bg-accent-subtle font-medium text-accent' : 'text-text-muted hover:text-text'
  }`

export function AppHeader({
  telemetry,
  offline,
  onOpenSettings,
}: {
  telemetry: TelemetrySummary | null
  offline: boolean
  onOpenSettings: () => void
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-surface/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-4 px-4 sm:px-6">
        <div className="flex items-center gap-2">
          <span className="h-4 w-1 rounded-full bg-accent" aria-hidden="true" />
          <span className="text-sm font-semibold tracking-tight text-text">
            Adaptive Copilot
          </span>
        </div>

        <nav className="flex items-center gap-1" aria-label="Primary">
          <NavLink to="/" className={navClass} end>
            Copilot
          </NavLink>
          <NavLink to="/grounding" className={navClass}>
            Grounding
          </NavLink>
        </nav>

        <div className="ml-auto flex items-center gap-4">
          <HeaderMonitor data={telemetry} offline={offline} />
          <div className="flex items-center gap-2 border-l border-border pl-4">
            <ThemeToggle />
            <button
              type="button"
              onClick={onOpenSettings}
              className="btn-ghost"
              aria-label="Open settings"
              title="Settings"
            >
              <Settings size={15} />
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}
