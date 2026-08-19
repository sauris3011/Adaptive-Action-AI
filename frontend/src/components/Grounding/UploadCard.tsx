import { RefreshCw, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { ApiError, api } from '../../lib/api'

/* Dynamic document upload and re-seed (FR-15).

   A rejected upload reports 422 with the reason, because the file IS stored -
   an unsupported modality is accepted and referenceable, just not interpreted
   yet (PRD 8.1). Saying "failed" would misdescribe what happened. */

interface Props {
  supported: string[]
  onChanged: () => void
}

export function UploadCard({ supported, onChanged }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<'upload' | 'reseed' | null>(null)
  const [message, setMessage] = useState<{ tone: 'ok' | 'warn' | 'error'; text: string } | null>(
    null,
  )

  async function handleFile(file: File) {
    setBusy('upload')
    setMessage(null)
    try {
      const result = await api.uploadDocument(file)
      setMessage({
        tone: 'ok',
        text: `${file.name}: ${result.chunks} chunks from ${result.documents.join(', ') || 'no document'}.`,
      })
      onChanged()
    } catch (cause) {
      const isStored = cause instanceof ApiError && cause.status === 422
      setMessage({
        tone: isStored ? 'warn' : 'error',
        text: isStored
          ? `${file.name} stored but not interpreted: ${cause.message}`
          : cause instanceof ApiError
            ? cause.message
            : String(cause),
      })
    } finally {
      setBusy(null)
      if (input.current) input.current.value = ''
    }
  }

  async function reseed() {
    setBusy('reseed')
    setMessage(null)
    try {
      const result = await api.reseed()
      setMessage({
        tone: 'ok',
        text: `Re-seeded: ${result.documents} documents, ${result.chunks} chunks, ${result.graph.nodes} nodes, ${result.graph.relationships} relationships.`,
      })
      onChanged()
    } catch (cause) {
      setMessage({ tone: 'error', text: cause instanceof ApiError ? cause.message : String(cause) })
    } finally {
      setBusy(null)
    }
  }

  const tone =
    message?.tone === 'ok' ? 'text-success' : message?.tone === 'warn' ? 'text-warning' : 'text-danger'

  return (
    <section className="card p-4">
      <header className="mb-3">
        <h2 className="text-sm font-semibold text-text">Documents</h2>
        <p className="mt-1 text-xs text-text-subtle">
          Uploaded documents are chunked by clause, embedded, and extracted into the graph. A
          document without a tier in its front matter is rejected: precedence is a property of the
          corpus, not a model judgement.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" onClick={() => input.current?.click()} disabled={busy !== null}>
          <Upload size={14} />
          {busy === 'upload' ? 'Ingesting' : 'Upload document'}
        </button>
        <button className="btn-ghost" onClick={reseed} disabled={busy !== null}>
          <RefreshCw size={14} />
          {busy === 'reseed' ? 'Re-seeding' : 'Re-seed domain pack'}
        </button>
        <input
          ref={input}
          type="file"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void handleFile(file)
          }}
        />
      </div>

      <p className="mt-3 text-[11px] text-text-subtle">
        Interpreted formats: {supported.join(', ') || 'none registered'}
      </p>
      {message && <p className={`mt-2 text-xs ${tone}`}>{message.text}</p>}
    </section>
  )
}
