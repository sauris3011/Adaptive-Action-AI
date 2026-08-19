import { TriangleAlert } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AnswerCard } from '../components/Grounding/AnswerCard'
import { GroundingRail } from '../components/Grounding/GroundingRail'
import { RetrievalPreview } from '../components/Grounding/RetrievalPreview'
import { UploadCard } from '../components/Grounding/UploadCard'
import { SplitLayout } from '../components/ui/SplitLayout'
import {
  ApiError,
  api,
  type GraphAnswer,
  type GraphMethod,
  type GroundingStats,
} from '../lib/api'

/* Ask the knowledge graph (FR-15).

   Plain language in, one of five audited queries out - and the call that ran is
   always on screen. That last part is what makes a wrong answer recoverable:
   the user retries by picking a different query, not by rewording and hoping.

   A failed query keeps the last good answer visible. Blanking the panel on
   error loses the thing the operator was reading and tells them nothing. */

const DEFAULT_QUESTION = 'Has anyone else disputed this merchant recently?'

export function GroundingPage() {
  const navigate = useNavigate()
  const handoff = (useLocation().state ?? null) as { merchant?: string } | null

  const [question, setQuestion] = useState(
    handoff?.merchant ? `What is the risk profile for ${handoff.merchant}?` : DEFAULT_QUESTION,
  )
  const [answer, setAnswer] = useState<GraphAnswer | null>(null)
  const [stats, setStats] = useState<GroundingStats | null>(null)
  const [hops, setHops] = useState(2)
  const [busy, setBusy] = useState(true)
  const [drilling, setDrilling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [attachedTo, setAttachedTo] = useState<string | null>(null)
  const [attachTarget, setAttachTarget] = useState<string | null>(null)
  const pending = useRef(0)

  const run = useCallback(
    async (text: string, options: { method?: GraphMethod; hops?: number } = {}) => {
      const ticket = ++pending.current
      setBusy(true)
      setAttachedTo(null)
      try {
        const next = await api.askGraph({
          question: text,
          method: options.method,
          hops: options.hops ?? hops,
        })
        if (ticket !== pending.current) return
        setAnswer(next)
        setError(null)
      } catch (cause) {
        if (ticket !== pending.current) return
        setError(cause instanceof ApiError ? cause.message : String(cause))
      } finally {
        if (ticket === pending.current) setBusy(false)
      }
    },
    [hops],
  )

  const loadStats = useCallback(async () => {
    try {
      setStats(await api.groundingStats())
    } catch {
      /* The rail degrades to em-dashes; the answer is the deliverable and must
         not be blocked on a counts call. */
    }
  }, [])

  useEffect(() => {
    void run(question)
    void loadStats()
    /* The case to file evidence against - most recent wins, and none is a real
       state on a fresh install. */
    api
      .cases()
      .then((list) => setAttachTarget(list.cases[0]?.case_id ?? null))
      .catch(() => setAttachTarget(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function changeHops(next: number) {
    const clamped = Math.max(1, Math.min(3, next))
    if (clamped === hops) return
    setHops(clamped)
    void run(question, {
      method: (answer?.resolved.method as GraphMethod) ?? undefined,
      hops: clamped,
    })
  }

  async function attach() {
    if (!answer || !attachTarget) return
    try {
      await api.attachEvidence(attachTarget, {
        resolved_call: answer.resolved.display,
        method: answer.resolved.method,
        entity: answer.resolved.entity,
        answer: answer.answer,
        backend: answer.backend,
      })
      setAttachedTo(attachTarget)
      setError(null)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
    }
  }

  async function drill() {
    if (!answer) return
    setDrilling(true)
    try {
      const result = await api.switchGraphBackend(answer.backend === 'kuzu' ? 'neo4j' : 'kuzu')
      setError(null)
      await loadStats()
      await run(question, { method: answer.resolved.method as GraphMethod })
      return result
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause))
    } finally {
      setDrilling(false)
    }
  }

  const method = answer?.resolved.method ?? null

  return (
    <SplitLayout
      rail={
        <GroundingRail
          stats={stats}
          answer={answer}
          selectedMethod={method}
          onPick={(picked) => void run(question, { method: picked as GraphMethod })}
          onDrill={() => void drill()}
          drilling={drilling}
          showDrill={import.meta.env.DEV}
        />
      }
    >
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-lg font-semibold tracking-[-0.01em] text-text">
          Ask the knowledge graph
        </h1>
        <span className="text-xs text-text-muted">
          Plain language, resolved to one of five audited queries.
        </span>
      </div>

      <form
        className="mt-4 flex gap-[9px]"
        onSubmit={(event) => {
          event.preventDefault()
          void run(question)
        }}
      >
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          aria-label="Ask the knowledge graph"
          placeholder={DEFAULT_QUESTION}
          className="min-w-0 flex-1 rounded-lg border-[1.5px] border-border-strong bg-bg px-[13px] py-3 text-[13.5px] text-text outline-none transition-shadow focus:border-accent focus:ring-[3px] focus:ring-accent-subtle"
        />
        <button type="submit" disabled={busy} className="btn-primary rounded-[7px] px-5 py-[11px]">
          {busy ? 'Asking…' : 'Ask'}
        </button>
      </form>

      <div className="mt-[11px] flex flex-wrap gap-[7px]">
        {(answer?.surface ?? []).map((query) => {
          const selected = query.id === method
          return (
            <button
              key={query.id}
              type="button"
              onClick={() => void run(question, { method: query.id as GraphMethod })}
              aria-pressed={selected}
              className={`rounded-[5px] border px-[9px] py-1 font-mono text-[11px] font-medium transition-colors ${
                selected
                  ? 'border-info bg-info-subtle text-info'
                  : 'border-border bg-surface text-text-muted hover:text-text'
              }`}
            >
              {query.id}
            </button>
          )
        })}
      </div>

      {answer && (
        <p className="mt-[9px] text-[11.5px] leading-relaxed text-text-muted">
          Resolved to{' '}
          <span className="font-mono text-[11.5px] text-info">{answer.resolved.display}</span> — the
          surface is five fixed queries, not a Cypher passthrough. Tap another to re-run.
        </p>
      )}

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-danger/40 bg-danger-subtle p-3 text-sm text-danger">
          <TriangleAlert size={16} className="mt-0.5 flex-none" aria-hidden="true" />
          <span>
            {error} The last good answer is still shown below — retry by tapping a query chip.
          </span>
        </div>
      )}

      {answer ? (
        <AnswerCard
          answer={answer}
          busy={busy}
          hops={hops}
          onHops={changeHops}
          onAttach={() => void attach()}
          onBackToLookup={() => navigate('/transactions')}
          attachTarget={attachTarget}
          attachedTo={attachedTo}
        />
      ) : (
        <div className="mt-[18px] rounded-[10px] border border-border bg-surface-raised px-5 py-12 text-center text-sm text-text-subtle">
          {busy ? 'Resolving the question…' : 'No answer yet. Ask a question above.'}
        </div>
      )}

      <p className="mt-[22px] max-w-[76ch] border-t border-dashed border-border pt-[14px] text-xs leading-relaxed text-text-muted [text-wrap:pretty]">
        Answer first, picture second. The sentence is the deliverable; the graph is corroboration an
        agent can point a team lead at. Showing the resolved call is what makes a wrong answer
        recoverable — the user retries by picking a different query, not by rewording and hoping.
      </p>

      {/* The corpus tools predate this screen and are still the only way to
          load a document or check what a query retrieves, so they stay - folded
          away rather than competing with the answer for the top of the page. */}
      <details className="mt-6 rounded-lg border border-border bg-surface-raised">
        <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-text">
          Corpus tools
        </summary>
        <div className="space-y-4 border-t border-border p-4">
          <RetrievalPreview />
          {stats && (
            <UploadCard supported={stats.supported_uploads} onChanged={() => void loadStats()} />
          )}
        </div>
      </details>
    </SplitLayout>
  )
}
