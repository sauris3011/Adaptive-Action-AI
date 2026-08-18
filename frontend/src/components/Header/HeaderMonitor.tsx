import { Activity, CircleDollarSign, Coins, WifiOff } from 'lucide-react'
import { formatCost, formatTokens, type TelemetrySummary } from '../../lib/api'

/* Global header LLM monitor (FR-13).
   Reads the backend's own SQLite ledger, not LiteLLM /spend and not LangSmith.
   An always-visible element must not depend on a SaaS round trip through a
   TLS-intercepting proxy (PRD 5.8). */

function Stat({
  icon,
  label,
  value,
  tone = 'default',
}: {
  icon: React.ReactNode
  label: string
  value: string
  tone?: 'default' | 'active'
}) {
  return (
    <div className="flex items-center gap-1.5" title={label}>
      <span className={tone === 'active' ? 'text-accent' : 'text-text-subtle'}>{icon}</span>
      <span className="label-eyebrow hidden lg:inline">{label}</span>
      <span className="tnum text-sm font-medium text-text">{value}</span>
    </div>
  )
}

export function HeaderMonitor({
  data,
  offline,
}: {
  data: TelemetrySummary | null
  offline: boolean
}) {
  if (offline) {
    return (
      <div className="flex items-center gap-1.5 text-danger" title="Backend unreachable">
        <WifiOff size={15} />
        <span className="text-sm font-medium">Backend offline</span>
      </div>
    )
  }

  if (!data) {
    return <div className="text-sm text-text-subtle">Connecting…</div>
  }

  const busy = data.active_calls > 0

  return (
    <div className="flex items-center gap-4 sm:gap-5">
      <Stat
        icon={
          <Activity size={15} className={busy ? 'animate-pulse' : undefined} />
        }
        label="Active"
        value={String(data.active_calls)}
        tone={busy ? 'active' : 'default'}
      />
      <Stat
        icon={<Coins size={15} />}
        label="Tokens"
        value={`${formatTokens(data.input_tokens)} / ${formatTokens(data.output_tokens)}`}
      />
      <Stat
        icon={<CircleDollarSign size={15} />}
        label="Est. cost"
        value={formatCost(data.estimated_cost_usd)}
      />
      {data.errors > 0 && (
        <span className="rounded bg-danger-subtle px-1.5 py-0.5 text-xs font-medium text-danger">
          {data.errors} error{data.errors === 1 ? '' : 's'}
        </span>
      )}
    </div>
  )
}
