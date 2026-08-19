import { useCallback, useEffect, useState } from 'react'
import { ForceGraph } from '../components/Grounding/ForceGraph'
import { RetrievalPreview } from '../components/Grounding/RetrievalPreview'
import { StatsPanel } from '../components/Grounding/StatsPanel'
import { UploadCard } from '../components/Grounding/UploadCard'
import { ApiError, api, type GraphNode, type GraphView, type GroundingStats } from '../lib/api'

/* Universal grounding panel (FR-15).

   One page covering all three stores, because "hybrid grounding" is a claim the
   operator should be able to check rather than take on trust. */

export function GroundingPage() {
  const [stats, setStats] = useState<GroundingStats | null>(null)
  const [view, setView] = useState<GraphView | null>(null)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [focus, setFocus] = useState<string | null>(null)
  const [hops, setHops] = useState(2)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [nextStats, nextView] = await Promise.all([
        api.groundingStats(),
        api.graphView(focus ?? undefined, hops),
      ])
      setStats(nextStats)
      setView(nextView)
      setError(null)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
    }
  }, [focus, hops])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-text">Grounding</h1>
        <p className="mt-1 text-sm text-text-muted">
          Policy passages, entity state, and the relationships between them. Every recommendation is
          grounded in these three stores.
        </p>
      </div>

      {error && (
        <div className="card border-danger/40 bg-danger-subtle p-3 text-sm text-danger">{error}</div>
      )}

      {stats && <StatsPanel stats={stats} />}

      <section className="card p-4">
        <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text">Knowledge graph</h2>
            <p className="mt-1 text-xs text-text-subtle">
              {focus
                ? `Neighbourhood of ${focus}, ${hops} hop${hops > 1 ? 's' : ''}.`
                : 'Full seed graph. The policy subgraph is deliberately separate from the entity subgraph.'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {focus && (
              <>
                <label className="text-xs text-text-muted" htmlFor="hops">
                  Hops
                </label>
                <select
                  id="hops"
                  className="field w-16 py-1"
                  value={hops}
                  onChange={(e) => setHops(Number(e.target.value))}
                >
                  <option value={1}>1</option>
                  <option value={2}>2</option>
                  <option value={3}>3</option>
                </select>
                <button
                  className="btn-ghost text-xs"
                  onClick={() => {
                    setFocus(null)
                    setSelected(null)
                  }}
                >
                  Show all
                </button>
              </>
            )}
          </div>
        </header>

        {view ? (
          <ForceGraph
            view={view}
            selectedId={selected?.id ?? null}
            onSelect={(node) => setSelected(node)}
          />
        ) : (
          <p className="py-12 text-center text-sm text-text-subtle">Loading graph.</p>
        )}

        {selected && (
          <div className="mt-4 rounded-md border border-border p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="label-eyebrow">{selected.label}</span>
              <span className="font-mono text-xs text-text">{selected.id}</span>
              <button
                className="btn-ghost ml-auto text-xs"
                onClick={() => setFocus(selected.id)}
                disabled={focus === selected.id}
              >
                Centre on this node
              </button>
            </div>
            <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
              {Object.entries(selected.props)
                .filter(([, value]) => value !== '' && value !== null && value !== undefined)
                .map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-4 text-xs">
                    <dt className="text-text-subtle">{key}</dt>
                    <dd className="tnum text-text">{String(value)}</dd>
                  </div>
                ))}
            </dl>
          </div>
        )}
      </section>

      <RetrievalPreview />

      {stats && <UploadCard supported={stats.supported_uploads} onChanged={() => void load()} />}
    </div>
  )
}
