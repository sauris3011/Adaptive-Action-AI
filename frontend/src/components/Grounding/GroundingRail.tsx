import { Eyebrow } from '../ui/Eyebrow'
import { KeyValueRow } from '../ui/KeyValueRow'
import { StatCard } from '../ui/StatCard'
import type { GraphAnswer, GroundingStats } from '../../lib/api'

/* Rail for the graph-search screen: what is loaded, which store is answering,
   and the five queries that store will answer with.

   The query list is rendered from the backend's own description of its surface
   rather than a copy kept here, so the rail cannot claim a query the store does
   not implement. */

export function GroundingRail({
  stats,
  answer,
  selectedMethod,
  onPick,
  onDrill,
  drilling,
  showDrill,
}: {
  stats: GroundingStats | null
  answer: GraphAnswer | null
  selectedMethod: string | null
  onPick: (method: string) => void
  onDrill: () => void
  drilling: boolean
  showDrill: boolean
}) {
  const backend = answer?.backend ?? stats?.graph.active_backend ?? stats?.graph.backend ?? '—'
  const onFallback = backend === 'kuzu'
  const surface = answer?.surface ?? []

  return (
    <div className="flex flex-col gap-4">
      <StatCard title="Grounding status">
        <KeyValueRow label="documents" value={stats?.vector.documents ?? '—'} />
        <KeyValueRow label="chunks" value={stats?.vector.chunks ?? '—'} />
        <KeyValueRow label="nodes" value={stats?.graph.nodes ?? '—'} />
        <KeyValueRow label="relationships" value={stats?.graph.relationships ?? '—'} />
        <KeyValueRow
          label="backend"
          value={onFallback ? 'Kùzu (embedded)' : backend === 'neo4j' ? 'Neo4j Aura' : backend}
          tone={onFallback ? 'warning' : 'success'}
        />
      </StatCard>

      {/* Dev build only. Flipping the store at runtime is a demo affordance for
          acceptance criterion 9, not something to leave reachable in a build
          someone might treat as real. */}
      {showDrill && (
        <button
          type="button"
          onClick={onDrill}
          disabled={drilling}
          className="btn-ghost w-full justify-start px-3 py-[9px] text-xs"
        >
          {drilling ? 'Switching store…' : 'Simulate fallback drill →'}
        </button>
      )}

      <div>
        <Eyebrow>The five queries</Eyebrow>
        <div className="mt-2 flex flex-col gap-1.5">
          {surface.map((query) => {
            const selected = query.id === selectedMethod
            return (
              <button
                key={query.id}
                type="button"
                onClick={() => onPick(query.id)}
                aria-pressed={selected}
                className={`card border-l-[3px] px-2.5 py-[9px] text-left transition-colors hover:bg-surface ${
                  selected ? 'border-l-info' : 'border-l-border-strong'
                }`}
              >
                <div className="font-mono text-[11.5px] font-semibold text-text">{query.id}</div>
                <div className="mt-0.5 text-[11.5px] leading-relaxed text-text-muted">
                  {query.description}
                </div>
              </button>
            )
          })}
        </div>
      </div>

      <p className="border-t border-border pt-[13px] text-[11.5px] leading-relaxed text-text-muted">
        A fixed surface is a deliberate constraint: the Kùzu fallback dialect diverges from Neo4j,
        so a passthrough would make the second backend unaffordable. The UI shows the constraint
        rather than hiding it.
      </p>
    </div>
  )
}
