import { Play, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { api } from '../lib/api'

/* Stage 1: the walking-skeleton probe.
   This exercises the whole LLM path - gateway, TLS policy, retries, guard,
   ledger - and moves the header monitor, which is the stage exit criterion.
   Stage 3 replaces this page with the dispute workflow. */

export function CopilotPage() {
  const [prompt, setPrompt] = useState('Reply with the single word: ready.')
  const [reply, setReply] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async () => {
    setBusy(true)
    setError(null)
    setReply(null)
    try {
      const result = await api.smoke(prompt)
      setReply(result.reply)
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-text">Copilot</h1>
        <p className="mt-1 text-sm text-text-muted">
          Card dispute intake, grounded reconciliation and the approval gate land here in Stage 3.
        </p>
      </div>

      <section className="card max-w-2xl space-y-4 p-5">
        <div>
          <h2 className="text-sm font-medium text-text">Gateway connectivity probe</h2>
          <p className="mt-1 text-xs text-text-muted">
            One round trip through LangChain to the LiteLLM gateway. Watch the header monitor.
          </p>
        </div>

        <textarea
          className="field min-h-[80px] resize-y font-mono text-xs"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          aria-label="Probe prompt"
        />

        <button type="button" className="btn-primary" onClick={run} disabled={busy}>
          <Play size={14} />
          {busy ? 'Calling…' : 'Send probe'}
        </button>

        {reply !== null && (
          <div className="rounded-md bg-success-subtle px-3 py-2">
            <p className="label-eyebrow text-success">Reply</p>
            <p className="mt-1 whitespace-pre-wrap text-sm text-text">{reply}</p>
          </div>
        )}

        {error && (
          <div className="flex gap-2 rounded-md bg-danger-subtle px-3 py-2">
            <TriangleAlert size={15} className="mt-0.5 shrink-0 text-danger" />
            <div>
              <p className="label-eyebrow text-danger">Call failed</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-xs text-text">{error}</p>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
