import { Clock, FileText } from 'lucide-react'
import { ACTION_LABELS, TIER_LABELS, type Evidence, type Recommendation } from '../../lib/api'

/* Recommendation, citations and confidence: FR-4 and FR-5.

   The approval controls live in ApprovalPanel rather than here, because what
   approving DOES belongs next to the decision, not tacked onto the end of the
   reasoning. */

function Confidence({ value }: { value: number }) {
  const tone = value >= 0.8 ? 'bg-success' : value >= 0.5 ? 'bg-warning' : 'bg-danger'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-border">
        <div className={`h-full ${tone}`} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="tnum text-xs text-text-muted">{(value * 100).toFixed(0)}%</span>
    </div>
  )
}

interface Props {
  recommendation: Recommendation
  evidence: Evidence[]
  elapsedMs: number
}

export function RecommendationCard({ recommendation, evidence, elapsedMs }: Props) {
  const byRef = new Map(evidence.map((e) => [e.ref, e]))

  return (
    <section className="card overflow-hidden">
      <header className="border-b border-border bg-surface px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="rounded bg-accent-subtle px-2 py-0.5 text-xs font-medium text-accent">
            {ACTION_LABELS[recommendation.action] ?? recommendation.action}
          </span>
          {recommendation.amount !== null && (
            <span className="tnum text-sm font-medium text-text">
              {recommendation.amount.toFixed(2)} USD
            </span>
          )}
          <span className="ml-auto flex items-center gap-1.5 text-xs text-text-subtle">
            <Clock size={12} />
            <span className="tnum">{(elapsedMs / 1000).toFixed(1)}s</span>
          </span>
        </div>
        <h2 className="mt-2 text-sm font-semibold leading-snug text-text">
          {recommendation.headline}
        </h2>
      </header>

      <div className="space-y-4 p-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <p className="label-eyebrow">Governing clause</p>
            <p className="mt-1 font-mono text-xs text-text">{recommendation.governing_clause}</p>
          </div>
          <div>
            <p className="label-eyebrow">Deadline</p>
            <p className="mt-1 text-xs text-text">{recommendation.deadline}</p>
          </div>
          <div>
            <p className="label-eyebrow">Confidence</p>
            <div className="mt-1.5">
              <Confidence value={recommendation.confidence} />
            </div>
          </div>
        </div>

        <div>
          <p className="label-eyebrow">Rationale</p>
          <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-text-muted">
            {recommendation.rationale}
          </p>
        </div>

        {recommendation.caveats && (
          <div className="rounded-md border border-border bg-surface p-3">
            <p className="label-eyebrow">Check before approving</p>
            <p className="mt-1 text-xs leading-relaxed text-text-muted">{recommendation.caveats}</p>
          </div>
        )}

        <div>
          <p className="label-eyebrow">Citations</p>
          <ul className="mt-1.5 space-y-1.5">
            {recommendation.citations.map((ref) => {
              const source = byRef.get(ref)
              return (
                <li key={ref} className="flex items-start gap-2 text-xs">
                  <FileText size={12} className="mt-0.5 shrink-0 text-text-subtle" />
                  <span className="font-mono text-text">{ref}</span>
                  {source ? (
                    <span className="text-text-subtle">
                      {source.title}
                      {source.tier !== null && ` - tier ${source.tier}, ${TIER_LABELS[source.tier]}`}
                    </span>
                  ) : (
                    /* FR-5 is only meaningful if a citation outside the evidence
                       is visible rather than assumed correct. */
                    <span className="text-warning">not in retrieved evidence</span>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      </div>

      <footer className="border-t border-border bg-surface px-4 py-2">
        <p className="text-xs text-text-subtle">
          {recommendation.requires_approval
            ? 'Requires approval. Nothing has executed - the run is paused before any action.'
            : 'No action to approve; this is an answer only.'}
        </p>
      </footer>
    </section>
  )
}
