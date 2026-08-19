import { Check, CircleCheck, CircleX, TriangleAlert, X } from 'lucide-react'
import { useState } from 'react'
import { ApiError, INSTRUMENT_LABELS, api, type PlannedAction, type Run } from '../../lib/api'

/* Approval gate controls (FR-17) and the action workflow's result (FR-7/FR-8).

   Two things this deliberately does that a simpler panel would not:

   1. It lists what approving WILL do BEFORE it happens. An approval gate that
      hides the consequences is a rubber stamp with extra steps.
   2. It shows the effect ledger after a rejection too - three empty lists. FR-8
      says a rejection performs no side effect, and an operator should be able
      to see that rather than trust it. */

const AGENT_LIMIT = 500

interface Props {
  run: Run
  onResolved: (run: Run) => void
}

function PlannedList({ steps }: { steps: PlannedAction[] }) {
  if (!steps.length) {
    return (
      <p className="text-xs text-text-subtle">
        This recommendation performs no action. There is nothing to execute on approval.
      </p>
    )
  }
  return (
    <ol className="space-y-1">
      {steps.map((step, i) => (
        <li key={`${step.instrument}-${i}`} className="flex items-baseline gap-2 text-xs">
          <span className="tnum text-text-subtle">{i + 1}.</span>
          <span className="text-text">{INSTRUMENT_LABELS[step.instrument] ?? step.instrument}</span>
        </li>
      ))}
    </ol>
  )
}

export function ApprovalPanel({ run, onResolved }: Props) {
  const [approver, setApprover] = useState('Priya Nair')
  const [role, setRole] = useState('agent')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const recommendation = run.recommendation
  const settled = run.status !== 'awaiting_approval'
  const amount = recommendation?.amount ?? 0
  const needsLead = amount > AGENT_LIMIT

  async function act(kind: 'approve' | 'reject') {
    if (!run.run_id) return
    if (kind === 'reject' && reason.trim().length < 3) {
      setError('A rejection reason is required - it is recorded on the case (FR-8).')
      return
    }
    setBusy(kind)
    setError(null)
    try {
      const next =
        kind === 'approve'
          ? await api.approveRun(run.run_id, { approver, approver_role: role })
          : await api.rejectRun(run.run_id, { approver, reason })
      onResolved(next)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setBusy(null)
    }
  }

  if (settled) {
    const approved = run.status.startsWith('approved')
    const failed = run.status === 'approved_action_failed'
    const effects = run.effects
    const effectCount = effects
      ? effects.provisional_credits.length +
        effects.dispute_cases.length +
        effects.notices.length
      : 0

    return (
      <section className="card p-4">
        <div className="flex items-start gap-2">
          {approved && !failed ? (
            <CircleCheck size={16} className="mt-0.5 shrink-0 text-success" />
          ) : failed ? (
            <TriangleAlert size={16} className="mt-0.5 shrink-0 text-warning" />
          ) : (
            <CircleX size={16} className="mt-0.5 shrink-0 text-text-muted" />
          )}
          <div className="min-w-0 flex-1">
            <p
              className={`label-eyebrow ${
                failed ? 'text-warning' : approved ? 'text-success' : 'text-text-muted'
              }`}
            >
              {failed ? 'Approved, action failed' : approved ? 'Approved' : 'Rejected'}
            </p>
            <p className="mt-1 text-sm text-text">
              {run.approver}
              {run.approved_at && (
                <span className="text-text-subtle"> - {new Date(run.approved_at).toLocaleString()}</span>
              )}
            </p>
            {run.reject_reason && (
              <p className="mt-1 text-xs text-text-muted">Reason: {run.reject_reason}</p>
            )}
            {run.case_id && (
              <p className="mt-1 font-mono text-[11px] text-text-subtle">{run.case_id}</p>
            )}

            {run.action_results.length > 0 && (
              <ul className="mt-3 space-y-1">
                {run.action_results.map((result) => (
                  <li key={result.reference || result.instrument} className="flex flex-wrap items-center gap-2 text-xs">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                        result.status_code === 200
                          ? 'bg-success-subtle text-success'
                          : 'bg-danger-subtle text-danger'
                      }`}
                    >
                      {result.status_code}
                    </span>
                    <span className="text-text">
                      {INSTRUMENT_LABELS[result.instrument] ?? result.instrument}
                    </span>
                    <span className="font-mono text-text-subtle">{result.reference}</span>
                    {result.idempotent && (
                      <span className="text-text-subtle">(already existed)</span>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {effects && (
              <p className="mt-3 text-[11px] text-text-subtle">
                Core-banking effects recorded for this run: {effectCount}
                {effectCount === 0 && ' - no side effect, as required on the rejection path.'}
              </p>
            )}
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="card p-4">
      <header className="mb-3">
        <h2 className="text-sm font-semibold text-text">Approval required</h2>
        <p className="mt-1 text-xs text-text-subtle">
          The run is paused at a durable checkpoint. Nothing has executed. Approving will perform
          exactly the steps below.
        </p>
      </header>

      <div className="rounded-md border border-border bg-surface p-3">
        <p className="label-eyebrow">On approval</p>
        <div className="mt-1.5">
          <PlannedList steps={run.planned_actions} />
        </div>
      </div>

      {needsLead && (
        <p className="mt-3 flex items-start gap-2 text-xs text-warning">
          <TriangleAlert size={13} className="mt-0.5 shrink-0" />
          BDP-3.4: {amount.toFixed(2)} USD exceeds the {AGENT_LIMIT} USD agent limit and requires
          Team Lead approval.
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          className="field w-44"
          value={approver}
          onChange={(e) => setApprover(e.target.value)}
          placeholder="Approver name"
          aria-label="Approver name"
        />
        <select
          className="field w-40"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          aria-label="Approver role"
        >
          <option value="agent">Agent</option>
          <option value="team_lead">Team Lead</option>
        </select>
      </div>

      <input
        className="field mt-2"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Rejection reason (required to reject)"
        aria-label="Rejection reason"
      />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          className="btn-primary"
          onClick={() => act('approve')}
          disabled={busy !== null || !recommendation}
        >
          <Check size={14} />
          {busy === 'approve' ? 'Executing' : 'Approve'}
        </button>
        <button
          className="btn-ghost"
          onClick={() => act('reject')}
          disabled={busy !== null || !recommendation}
        >
          <X size={14} />
          {busy === 'reject' ? 'Recording' : 'Reject'}
        </button>
      </div>

      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </section>
  )
}
