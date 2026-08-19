import { Database, GitBranch, Layers, TriangleAlert } from 'lucide-react'
import type { GroundingStats } from '../../lib/api'

/* Vector, graph and relational counts side by side (FR-15).

   Acceptance criterion 3 says these must match what seed_data.py printed. They
   are read straight from the stores on every poll, so a mismatch is a real
   defect rather than a stale cache. */

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="tnum text-sm font-medium text-text">{value}</span>
    </div>
  )
}

function Panel({
  title,
  icon,
  subtitle,
  children,
}: {
  title: string
  icon: React.ReactNode
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <section className="card p-4">
      <header className="mb-3 flex items-center gap-2">
        <span className="text-text-muted">{icon}</span>
        <h2 className="text-sm font-semibold text-text">{title}</h2>
      </header>
      {subtitle && <p className="mb-2 text-xs text-text-subtle">{subtitle}</p>}
      <div className="divide-y divide-border">{children}</div>
    </section>
  )
}

export function StatsPanel({ stats }: { stats: GroundingStats }) {
  const { vector, graph, relational } = stats
  const flaggedNote = 'Fraud flags live here and in no policy document.'

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Panel
        title="Vector"
        icon={<Layers size={15} />}
        subtitle={`${vector.collection} - ${vector.embedder.backend} (${vector.embedder.dimension}d)`}
      >
        <Metric label="Documents" value={vector.documents} />
        <Metric label="Chunks" value={vector.chunks} />
        {Object.entries(vector.by_tier)
          .sort()
          .map(([tier, count]) => (
            <Metric key={tier} label={tier} value={count} />
          ))}
        {vector.embedder.degraded && (
          <p className="flex items-start gap-2 pt-2 text-xs text-warning">
            <TriangleAlert size={13} className="mt-0.5 shrink-0" />
            Degraded embedder: lexical hashing only. Retrieval quality is materially reduced.
          </p>
        )}
      </Panel>

      <Panel
        title="Knowledge graph"
        icon={<GitBranch size={15} />}
        subtitle={`Backend: ${graph.active_backend ?? graph.backend}`}
      >
        <Metric label="Nodes" value={graph.nodes} />
        <Metric label="Relationships" value={graph.relationships} />
        {Object.entries(graph.by_label).map(([label, count]) => (
          <Metric key={label} label={label} value={count} />
        ))}
      </Panel>

      <Panel title="Relational" icon={<Database size={15} />} subtitle={flaggedNote}>
        {Object.entries(relational).map(([table, count]) => (
          <Metric key={table} label={table} value={count} />
        ))}
      </Panel>
    </div>
  )
}
