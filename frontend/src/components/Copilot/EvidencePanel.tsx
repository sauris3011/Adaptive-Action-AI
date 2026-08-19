import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { TIER_LABELS, type Evidence } from '../../lib/api'

/* What the recommendation was actually grounded in (US-4, FR-9).

   Collapsed by default: Priya reviews the recommendation, Aisha reads the
   evidence. Ordered by precedence rather than similarity, because that is the
   order that decided the outcome. */

const KIND_STYLE: Record<Evidence['kind'], string> = {
  policy: 'bg-accent-subtle text-accent',
  graph: 'bg-info-subtle text-info',
  record: 'bg-success-subtle text-success',
}

export function EvidencePanel({ evidence }: { evidence: Evidence[] }) {
  const [open, setOpen] = useState(false)
  const counts = evidence.reduce<Record<string, number>>((acc, e) => {
    acc[e.kind] = (acc[e.kind] ?? 0) + 1
    return acc
  }, {})

  return (
    <section className="card">
      <button
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        <span className="text-sm font-medium text-text">Evidence</span>
        <span className="text-xs text-text-subtle">
          {evidence.length} items - {counts.policy ?? 0} policy, {counts.graph ?? 0} graph,{' '}
          {counts.record ?? 0} record
        </span>
      </button>

      {open && (
        <ul className="space-y-2 border-t border-border p-4">
          {evidence.map((item) => (
            <li key={`${item.kind}-${item.ref}`} className="rounded-md border border-border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${KIND_STYLE[item.kind]}`}
                >
                  {item.kind}
                </span>
                <span className="font-mono text-xs text-text">{item.ref}</span>
                {item.tier !== null && (
                  <span className="text-[11px] text-text-subtle">
                    tier {item.tier} - {TIER_LABELS[item.tier]}
                  </span>
                )}
                {item.score !== null && (
                  <span className="tnum ml-auto text-[11px] text-text-subtle">
                    {item.score.toFixed(3)}
                  </span>
                )}
              </div>
              <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-text-muted">
                {item.content}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
