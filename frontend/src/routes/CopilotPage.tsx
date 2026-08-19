import { Send, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { ApprovalPanel } from '../components/Copilot/ApprovalPanel'
import { ConflictBanner } from '../components/Copilot/ConflictBanner'
import { EvidencePanel } from '../components/Copilot/EvidencePanel'
import { RecommendationCard } from '../components/Copilot/RecommendationCard'
import { ApiError, api, type Run } from '../lib/api'

/* Dispute intake and grounded recommendation (US-1, US-2, US-5).

   Order on the page is deliberate: the conflict banner sits ABOVE the
   recommendation. Per PRD 1.4 the reconciliation is the product, so a reviewer
   should see that sources disagreed before they see what was decided - not
   discover it in a footnote afterwards. */

/* Two shapes on purpose. A scenario phrased as a QUESTION returns answer_only
   with nothing to approve (US-5); one phrased as a REQUEST TO ACT reaches the
   approval gate (US-1). Both are correct, and the difference is worth showing. */
const SCENARIOS = [
  {
    label: 'Fraud routing (C3)',
    text: 'Cardholder A. Sharma says she did not authorise a 420 USD charge from Cobalt Travel on her Signature card. Please open the dispute and put it right.',
    transaction_id: 'TXN-9001',
    customer_id: 'CUST-1001',
  },
  {
    label: 'Credit timing (C1)',
    text: 'A. Sharma ordered a 189.99 USD item from Northwind Electronics and it never arrived. Please open the dispute and apply provisional credit.',
    transaction_id: 'TXN-9002',
    customer_id: 'CUST-1001',
  },
  {
    label: 'Small refund (C2)',
    text: 'R. Okafor disputes a 34.50 USD Aurora Streaming charge for content never received. Please refund him.',
    transaction_id: 'TXN-9003',
    customer_id: 'CUST-1002',
  },
  {
    label: 'Above agent limit (BDP-3.4)',
    text: 'M. Lindqvist reports an unauthorised 899 USD charge at Northwind Electronics on a new Signature account. Please open the dispute and issue provisional credit.',
    transaction_id: 'TXN-9004',
    customer_id: 'CUST-1003',
  },
  {
    label: 'Policy question (US-5)',
    text: 'When do we have to give a Signature cardholder provisional credit on a disputed transaction?',
    transaction_id: 'TXN-9002',
    customer_id: 'CUST-1001',
  },
]

/* The look-up screen hands a transaction over rather than running it itself:
   whether a request is a question or an instruction to act is what decides
   between answer_only and the approval gate, and that phrasing is the
   operator's to write. */
interface Handoff {
  text?: string
  transaction_id?: string
  customer_id?: string
}

export function CopilotPage() {
  const handoff = (useLocation().state ?? null) as Handoff | null
  const { runId } = useParams()
  const [text, setText] = useState(handoff?.text ?? SCENARIOS[0].text)
  const [transactionId, setTransactionId] = useState(
    handoff?.transaction_id ?? SCENARIOS[0].transaction_id,
  )
  const [customerId, setCustomerId] = useState(
    handoff?.customer_id ?? SCENARIOS[0].customer_id,
  )
  const [run, setRun] = useState<Run | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /* A run id in the URL is a run somebody else started - from the look-up
     screen, or from this tab before it was reloaded. It is read back from the
     checkpoint rather than held in memory, which is the property the durable
     gate was built for and the reason a reload does not lose a pending
     approval. */
  useEffect(() => {
    if (!runId) return
    let current = true
    setBusy(true)
    setError(null)
    api
      .getRun(runId)
      .then((recovered) => {
        if (!current) return
        setRun(recovered)
        setText(recovered.request_text ?? '')
        setTransactionId(recovered.transaction_id ?? '')
        setCustomerId(recovered.customer_id ?? '')
      })
      .catch((cause) => {
        if (current) setError(cause instanceof ApiError ? cause.message : String(cause))
      })
      .finally(() => {
        if (current) setBusy(false)
      })
    return () => {
      current = false
    }
  }, [runId])

  async function submit() {
    if (text.trim().length < 4) return
    setBusy(true)
    setError(null)
    setRun(null)
    try {
      setRun(
        await api.submitDispute({
          text,
          transaction_id: transactionId || null,
          customer_id: customerId || null,
        }),
      )
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-text">
          {runId ? 'Reviewing a pending run' : 'Copilot'}
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          {runId ? (
            <>
              Recovered from its checkpoint, not from this tab&apos;s memory — reload and it is
              still here.{' '}
              <Link to="/" className="font-medium text-accent hover:text-accent-hover">
                Raise a new dispute instead
              </Link>
              .
            </>
          ) : (
            <>
              Submit a dispute in plain language. The copilot grounds itself in policy, entity state
              and the transaction record, reconciles conflicting sources, and recommends an action
              for your approval.
            </>
          )}
        </p>
      </div>

      {/* Not rendered while reviewing a recovered run. Leaving the intake form
          here would offer "Submit dispute" as the obvious next click on a
          screen whose whole point is a dispute that already exists - which is
          how one transaction acquires two runs. Unmounted rather than hidden,
          so there are no focusable inputs behind a display:none. */}
      {!runId && (
      <section className="card space-y-3 p-4">
        <div className="flex flex-wrap gap-2">
          {SCENARIOS.map((scenario) => (
            <button
              key={scenario.label}
              className="btn-ghost text-xs"
              onClick={() => {
                setText(scenario.text)
                setTransactionId(scenario.transaction_id)
                setCustomerId(scenario.customer_id)
              }}
            >
              {scenario.label}
            </button>
          ))}
        </div>

        <textarea
          className="field min-h-[92px] resize-y text-sm"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Describe the dispute in the cardholder's own terms"
          aria-label="Dispute description"
        />

        <div className="flex flex-wrap items-center gap-2">
          <input
            className="field w-44"
            value={transactionId}
            onChange={(e) => setTransactionId(e.target.value)}
            placeholder="Transaction ID"
            aria-label="Transaction ID"
          />
          <input
            className="field w-44"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            placeholder="Customer ID"
            aria-label="Customer ID"
          />
          <button className="btn-primary" onClick={submit} disabled={busy}>
            <Send size={14} />
            {busy ? 'Reasoning' : 'Submit dispute'}
          </button>
          {busy && (
            <span className="text-xs text-text-subtle">
              Triage, retrieval, reconciliation, recommendation.
            </span>
          )}
        </div>
      </section>
      )}

      {error && (
        <div className="card flex gap-2 border-danger/40 bg-danger-subtle p-3">
          <TriangleAlert size={15} className="mt-0.5 shrink-0 text-danger" />
          <div className="min-w-0">
            <p className="label-eyebrow text-danger">Run failed</p>
            <p className="mt-1 whitespace-pre-wrap break-words text-xs text-text">{error}</p>
          </div>
        </div>
      )}

      {run && (
        <div className="space-y-4">
          {run.reconciliation && (
            <ConflictBanner
              conflicts={run.reconciliation.conflicts}
              notes={run.reconciliation.notes}
            />
          )}
          {run.recommendation && (
            <RecommendationCard
              recommendation={run.recommendation}
              evidence={run.evidence}
              elapsedMs={run.elapsed_ms}
            />
          )}
          {run.recommendation && <ApprovalPanel run={run} onResolved={setRun} />}
          <EvidencePanel evidence={run.evidence} />
          <p className="px-1 text-[11px] text-text-subtle">
            Run {run.run_id} - {run.status.replace(/_/g, ' ')}
          </p>
        </div>
      )}
    </div>
  )
}
