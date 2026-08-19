import { Search } from 'lucide-react'
import { useState } from 'react'
import { ApiError, TIER_LABELS, api, type Evidence } from '../../lib/api'

/* Retrieval preview.

   Counts alone prove the stores are populated, not that they are useful. This
   runs the exact hybrid fan-out the agent will use and shows what comes back,
   ordered by the precedence ladder rather than by similarity - which is the
   product thesis made visible one stage before the reconciler exists. */

const KIND_STYLE: Record<Evidence['kind'], string> = {
  policy: 'bg-accent-subtle text-accent',
  graph: 'bg-info-subtle text-info',
  record: 'bg-success-subtle text-success',
}

const EXAMPLES = [
  { label: 'C1 - credit timing', q: 'provisional credit timing for a Signature cardholder', txn: 'TXN-9002' },
  { label: 'C2 - merchant contact', q: 'refund under 50 USD for goods not received', txn: 'TXN-9003' },
  { label: 'C3 - fraud routing', q: 'unauthorised transaction with a fraud engine flag', txn: 'TXN-9001' },
]

export function RetrievalPreview() {
  const [query, setQuery] = useState(EXAMPLES[2].q)
  const [txn, setTxn] = useState(EXAMPLES[2].txn)
  const [results, setResults] = useState<Evidence[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(q = query, transaction = txn) {
    if (q.trim().length < 2) return
    setBusy(true)
    setError(null)
    try {
      const data = await api.groundingSearch(q, transaction || undefined)
      setResults(data.evidence)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
      setResults(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card p-4">
      <header className="mb-3">
        <h2 className="text-sm font-semibold text-text">Retrieval preview</h2>
        <p className="mt-1 text-xs text-text-subtle">
          The same parallel fan-out the agent uses: vector, graph and relational. Ordered by the
          precedence ladder, not by similarity score.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        <input
          className="field flex-1 min-w-[220px]"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
          placeholder="Ask what the corpus says"
          aria-label="Retrieval query"
        />
        <input
          className="field w-40"
          value={txn}
          onChange={(e) => setTxn(e.target.value)}
          placeholder="Transaction ID"
          aria-label="Transaction ID"
        />
        <button className="btn-primary" onClick={() => run()} disabled={busy}>
          <Search size={14} />
          {busy ? 'Retrieving' : 'Retrieve'}
        </button>
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example.label}
            className="btn-ghost text-xs"
            onClick={() => {
              setQuery(example.q)
              setTxn(example.txn)
              void run(example.q, example.txn)
            }}
          >
            {example.label}
          </button>
        ))}
      </div>

      {error && <p className="mt-3 text-sm text-danger">{error}</p>}

      {results && (
        <ul className="mt-4 space-y-2">
          {results.map((item) => (
            <li key={`${item.kind}-${item.ref}`} className="rounded-md border border-border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${KIND_STYLE[item.kind]}`}>
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
                {item.content.length > 320 ? `${item.content.slice(0, 320)}...` : item.content}
              </p>
            </li>
          ))}
          {!results.length && (
            <li className="text-sm text-text-subtle">Nothing retrieved for that query.</li>
          )}
        </ul>
      )}
    </section>
  )
}
