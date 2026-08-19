import { Minus, Paperclip, Plus } from 'lucide-react'
import { Eyebrow } from '../ui/Eyebrow'
import { NoticeStrip } from '../ui/NoticeStrip'
import { ToneTag } from '../ui/ToneTag'
import { ForceGraph } from './ForceGraph'
import type { GraphAnswer } from '../../lib/api'

/* Answer first, picture second.

   The sentence is the deliverable; the neighbourhood is corroboration an agent
   can point a team lead at. Inverting them - graph on top, answer underneath -
   was the version that made people read the picture and guess, which is exactly
   the failure this screen exists to remove. */

/* Beyond this the picture stops being readable, so the rest is reported as a
   count instead of drawn. */
const MAX_DRAWN_NODES = 24

function Skeleton() {
  return (
    <div className="animate-pulse space-y-2" aria-hidden="true">
      <div className="h-4 w-full rounded bg-border" />
      <div className="h-4 w-11/12 rounded bg-border" />
      <div className="h-4 w-2/3 rounded bg-border" />
    </div>
  )
}

export function AnswerCard({
  answer,
  busy,
  hops,
  onHops,
  onAttach,
  onBackToLookup,
  attachTarget,
  attachedTo,
}: {
  answer: GraphAnswer
  busy: boolean
  hops: number
  onHops: (next: number) => void
  onAttach: () => void
  onBackToLookup: () => void
  /* The case this answer would be filed against - null until one exists, which
     is a real state on a fresh install rather than an error. */
  attachTarget: string | null
  attachedTo: string | null
}) {
  const view = answer.view
  const latency = answer.latency_ms == null ? '' : ` · ${Math.round(answer.latency_ms)}ms`
  const backendNote = `${answer.backend === 'kuzu' ? 'Kùzu fallback' : answer.backend}${latency}`

  return (
    <div className="mt-[18px] overflow-hidden rounded-[10px] border border-border bg-surface-raised">
      <div className="border-b border-border px-5 py-[18px]">
        <Eyebrow>Answer</Eyebrow>
        <div className="mt-1.5 max-w-[70ch]">
          {busy ? (
            <Skeleton />
          ) : (
            <p className="text-[15px] leading-relaxed text-text [text-wrap:pretty]">
              {answer.answer}
            </p>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {answer.tags.map((tag) => (
            <ToneTag key={tag.label} tone={tag.tone}>
              {tag.label}
            </ToneTag>
          ))}
        </div>
      </div>

      <div className="px-5 pb-[18px] pt-[14px]">
        <div className="flex flex-wrap items-baseline gap-2.5">
          <Eyebrow>Neighbourhood</Eyebrow>
          <span className="tnum font-mono text-[11px] text-text-subtle">
            {view.hops ?? hops} hop · {view.nodes.length} nodes · {view.links.length} edges
          </span>
          <div className="ml-auto flex gap-[7px]">
            <button
              type="button"
              onClick={() => onHops(hops - 1)}
              disabled={hops <= 1 || busy}
              className="btn-ghost px-[11px] py-1.5 text-[11.5px]"
              aria-label="One hop fewer"
            >
              <Minus size={12} aria-hidden="true" /> hop
            </button>
            <button
              type="button"
              onClick={() => onHops(hops + 1)}
              disabled={hops >= 3 || busy}
              className="btn-ghost px-[11px] py-1.5 text-[11.5px]"
              aria-label="One hop more"
            >
              <Plus size={12} aria-hidden="true" /> hop
            </button>
          </div>
        </div>

        <div className="mt-2.5 overflow-hidden rounded-[9px] border border-border bg-surface p-2">
          <ForceGraph
            view={view}
            rootId={answer.resolved.entity}
            maxNodes={MAX_DRAWN_NODES}
          />
        </div>

        <div className="mt-[13px] flex flex-wrap items-center gap-[9px]">
          <button
            type="button"
            onClick={onAttach}
            disabled={busy || !view.found || !attachTarget}
            title={attachTarget ? undefined : 'No case has been opened yet'}
            className="btn-ghost px-[14px] py-2 text-[12.5px]"
          >
            <Paperclip size={13} aria-hidden="true" />
            {attachTarget ? `Attach to ${attachTarget}` : 'Attach to case'}
          </button>
          <button
            type="button"
            onClick={onBackToLookup}
            className="btn-ghost px-[14px] py-2 text-[12.5px]"
          >
            Back to look-up
          </button>
          <span className="ml-auto font-mono text-[11px] text-text-subtle">{backendNote}</span>
        </div>

        {attachedTo && (
          <div className="mt-3">
            <NoticeStrip>
              Attached to {attachedTo} as graph evidence. The resolved call and its result are now
              in the case trace.
            </NoticeStrip>
          </div>
        )}
      </div>
    </div>
  )
}
