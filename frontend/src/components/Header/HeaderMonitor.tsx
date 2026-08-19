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

/* Health sits left of the counters and is the loudest item in the strip.
   Gateway and graph state are what fail during a live demo; cost never needs to
   be read urgently, which is why it stays the quietest. */
function Health({ data }: { data: TelemetrySummary }) {
  const degraded = data.graph_fallback
  const tone = degraded ? 'text-warning' : 'text-success'
  const dot = degraded ? 'bg-warning' : 'bg-success'
  const label = degraded
    ? `graph: ${data.graph_backend === 'kuzu' ? 'Kùzu' : data.graph_backend} fallback`
    : data.gateway_enabled
      ? 'gateway ok'
      : 'gateway off'

  return (
    <div className="flex items-center gap-[7px]" title={`Graph backend: ${data.graph_backend}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" />
      <span className={`font-mono text-xs font-medium ${tone}`}>{label}</span>
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
      <Health data={data} />
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
