import { TriangleAlert } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ResultsTable } from '../components/Transactions/ResultsTable'
import { TransactionRail } from '../components/Transactions/TransactionRail'
import { Eyebrow } from '../components/ui/Eyebrow'
import { SegmentedControl } from '../components/ui/SegmentedControl'
import { SplitLayout } from '../components/ui/SplitLayout'
import { ApiError, SCOPES, api, type Scope, type TransactionRow } from '../lib/api'

/* Transaction look-up (FR-2, the structured half of grounding).

   One field over the system of record. The alternative - separate inputs for
   card, reference, amount and merchant - asks the operator to classify what
   they are holding before they can search with it, which is the step they are
   least able to do while a cardholder is on the line.

   Filtering is a server round trip on every keystroke rather than a local
   slice, because the duplicate rule belongs next to the table it reads and the
   query shape should not change when the record outgrows a fixture. */

const DEBOUNCE_MS = 180

export function TransactionsPage() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [scope, setScope] = useState<Scope>('30d')
  const [rows, setRows] = useState<TransactionRow[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const latest = useRef(0)

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      const ticket = ++latest.current
      setLoading(true)
      try {
        const result = await api.lookupTransactions(query, scope)
        /* Keystrokes can land out of order; only the newest response may paint. */
        if (ticket !== latest.current) return
        setRows(result.transactions)
        setError(null)
      } catch (cause) {
        if (ticket !== latest.current) return
        setError(cause instanceof ApiError ? cause.message : String(cause))
      } finally {
        if (ticket === latest.current) setLoading(false)
      }
    }, DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [query, scope])

  /* A selection that has fallen out of the filtered set is not a selection.
     Keeping the rail populated from a row the operator can no longer see is how
     an action gets taken against the wrong transaction. */
  const selected = useMemo(
    () => rows.find((row) => row.transaction_id === selectedId) ?? null,
    [rows, selectedId],
  )
  const scopeNote = SCOPES.find((s) => s.id === scope)?.note ?? scope

  /* The run parks at the approval gate, so this hands the operator straight to
     it rather than announcing an id and stopping. Announcing was the whole bug:
     the run existed, nothing linked to it, and the only way back was to retype
     the dispute on the copilot screen - which opened a second run against the
     same transaction. */
  async function openDispute() {
    if (!selected || selected.disputed) return
    setSubmitting(true)
    setError(null)
    try {
      const run = await api.submitDispute({
        text:
          `Cardholder ${selected.customer_name ?? selected.customer_id} disputes a ` +
          `${selected.amount.toFixed(2)} ${selected.currency} charge from ` +
          `${selected.merchant_name} on ${selected.posted_at}. Please open the dispute.`,
        transaction_id: selected.transaction_id,
        customer_id: selected.customer_id,
      })
      navigate(`/copilot/${run.run_id}`)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
      setSubmitting(false)
    }
  }

  function askCopilot() {
    if (!selected) return
    /* Hand the transaction over pre-bound rather than running it here: the
       phrasing of the request is what decides between an answer and an action,
       and that is the operator's call to make on the copilot screen. */
    navigate('/', {
      state: {
        text:
          `About ${selected.transaction_id}: a ${selected.amount.toFixed(2)} ` +
          `${selected.currency} charge from ${selected.merchant_name} on ${selected.posted_at}. `,
        transaction_id: selected.transaction_id,
        customer_id: selected.customer_id,
      },
    })
  }

  return (
    <SplitLayout
      rail={
        <TransactionRail
          row={selected}
          onAskGraph={(merchant) => navigate('/grounding', { state: { merchant } })}
        />
      }
    >
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-lg font-semibold tracking-[-0.01em] text-text">Transaction look-up</h1>
        <span className="text-xs text-text-muted">
          One field — card, reference, amount, or merchant.
        </span>
      </div>

      <div className="mt-4 flex items-center gap-[9px]">
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search the transaction record"
          placeholder="····5001 · TXN-9001 · 420.00 · Cobalt"
          className="min-w-0 flex-1 rounded-lg border-[1.5px] border-border-strong bg-bg px-[13px] py-[11px] font-mono text-[13px] text-text outline-none transition-shadow focus:border-accent focus:ring-[3px] focus:ring-accent-subtle"
        />
        <SegmentedControl
          label="Date window"
          value={scope}
          options={SCOPES}
          onChange={(next) => setScope(next)}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-baseline gap-2.5">
        <Eyebrow>Results</Eyebrow>
        <span className="tnum font-mono text-xs text-text-muted">
          {rows.length} transaction{rows.length === 1 ? '' : 's'}
        </span>
        <span className="ml-auto font-mono text-[11px] text-text-subtle">
          SQLite · authoritative record · {scopeNote}
        </span>
      </div>

      <ResultsTable
        rows={rows}
        selectedId={selected?.transaction_id ?? null}
        onSelect={(row) => {
          setSelectedId(row.transaction_id)
          setError(null)
        }}
        query={query}
        scopeNote={scopeNote}
        onClearQuery={() => setQuery('')}
        loading={loading}
      />

      <div className="mt-[14px] flex flex-wrap items-center gap-[9px]">
        <button
          type="button"
          onClick={openDispute}
          disabled={!selected || submitting || selected.disputed}
          className="btn-primary px-4 py-[9px] text-[13px]"
        >
          {submitting ? 'Opening…' : 'Open as dispute'}
        </button>
        {/* The route back to a case already in flight. Without it the operator's
            only way to reach the gate is to raise the dispute again, which is
            how one transaction ends up with two runs and two credits. */}
        {selected?.disputed && selected.dispute_run_id && (
          <button
            type="button"
            onClick={() => navigate(`/copilot/${selected.dispute_run_id}`)}
            className="btn-ghost px-4 py-[9px] text-[13px]"
          >
            Open the pending case
          </button>
        )}
        <button
          type="button"
          onClick={askCopilot}
          disabled={!selected}
          className="btn-ghost px-4 py-[9px] text-[13px]"
        >
          Ask copilot about this
        </button>
        <span className="font-mono text-[11.5px] text-text-subtle">
          {!selected
            ? 'select a row first'
            : selected.disputed
              ? `${selected.dispute_id} already open on ${selected.transaction_id}`
              : `${selected.transaction_id} selected`}
        </span>
      </div>

      {error && (
        <div className="mt-[14px] flex items-start gap-2 rounded-lg border border-danger/40 bg-danger-subtle p-3 text-sm text-danger">
          <TriangleAlert size={16} className="mt-0.5 flex-none" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <p className="mt-[22px] max-w-[76ch] border-t border-dashed border-border pt-[14px] text-xs leading-relaxed text-text-muted [text-wrap:pretty]">
        Signals are computed on the record, not by the model:{' '}
        <span className="font-mono text-[11.5px] text-danger">FRAUD</span> is the engine flag that
        overrides dispute intake,{' '}
        <span className="font-mono text-[11.5px] text-info">DISPUTED</span> is a case already open
        against this transaction, and{' '}
        <span className="font-mono text-[11.5px] text-warning">DUPLICATE</span> is same merchant,
        same amount, within 7 days. All three change the recommended route before any LLM call,
        which is why they belong in the list rather than a detail page.
      </p>
    </SplitLayout>
  )
}
