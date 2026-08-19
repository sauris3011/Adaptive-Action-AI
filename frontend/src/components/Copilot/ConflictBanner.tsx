import { GitCompareArrows, ShieldCheck, TriangleAlert } from 'lucide-react'
import { TIER_LABELS, type Conflict } from '../../lib/api'

/* Conflict banner (FR-16).

   Not in the master prompt. Added because PRD 1.4 makes reconciliation the
   product, and an invisible differentiator is not a differentiator: a copilot
   that silently picks the higher-ranked chunk looks identical to one that
   reconciles, right up until it is wrong.

   The losing source is shown beside the governing one deliberately. Stating
   only the winner would be indistinguishable from ordinary RAG. */

function ConflictCard({ conflict }: { conflict: Conflict }) {
  const isTrue = conflict.is_true_conflict
  const tone = isTrue
    ? { border: 'border-warning/40', bg: 'bg-warning-subtle', text: 'text-warning' }
    : { border: 'border-info/40', bg: 'bg-info-subtle', text: 'text-info' }

  return (
    <div className={`rounded-md border ${tone.border} ${tone.bg} p-3`}>
      <div className="flex items-start gap-2">
        {isTrue ? (
          <TriangleAlert size={15} className={`mt-0.5 shrink-0 ${tone.text}`} />
        ) : (
          <GitCompareArrows size={15} className={`mt-0.5 shrink-0 ${tone.text}`} />
        )}
        <div className="min-w-0 flex-1">
          <p className={`label-eyebrow ${tone.text}`}>
            {isTrue ? 'Sources conflict' : 'Apparent conflict only'}
          </p>
          <p className="mt-1 text-sm text-text">{conflict.description}</p>

          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <div className="rounded border border-border bg-surface-raised p-2">
              <p className="label-eyebrow text-success">Governs</p>
              <p className="mt-1 font-mono text-xs text-text">{conflict.governing_clause}</p>
              <p className="mt-0.5 text-[11px] text-text-subtle">
                Tier {conflict.governing_tier} - {TIER_LABELS[conflict.governing_tier]}
              </p>
            </div>
            <div className="rounded border border-border bg-surface-raised p-2">
              <p className="label-eyebrow text-text-subtle">
                {isTrue ? 'Does not govern' : 'Different instrument'}
              </p>
              <p className="mt-1 font-mono text-xs text-text">
                {conflict.superseded_clauses.join(', ') || 'none'}
              </p>
            </div>
          </div>

          <p className="mt-2 text-xs leading-relaxed text-text-muted">
            <span className="font-medium text-text">Why: </span>
            {conflict.resolution_basis}
          </p>
        </div>
      </div>
    </div>
  )
}

export function ConflictBanner({ conflicts, notes }: { conflicts: Conflict[]; notes: string }) {
  if (!conflicts.length) {
    return (
      <div className="flex items-start gap-2 rounded-md border border-border bg-surface p-3">
        <ShieldCheck size={15} className="mt-0.5 shrink-0 text-success" />
        <div>
          <p className="label-eyebrow text-success">No contradictions detected</p>
          <p className="mt-1 text-xs text-text-muted">
            {notes || 'The retrieved sources agree on the governing rule.'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {conflicts.map((conflict, i) => (
        <ConflictCard key={`${conflict.governing_clause}-${i}`} conflict={conflict} />
      ))}
      {notes && <p className="px-1 text-xs text-text-subtle">{notes}</p>}
    </div>
  )
}
