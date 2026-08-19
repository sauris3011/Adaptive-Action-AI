import './_api'
import { RetrievalPreview } from 'adaptive-action-copilot-ui'
import { OpenOnMount } from './_open'

/* The same parallel fan-out the agent uses — vector, graph and relational —
   ordered by the precedence ladder rather than by similarity score. */

export function Idle() {
  return <RetrievalPreview />
}

export function WithResults() {
  /* Clicks the real Retrieve control so the card shows the populated result
     list, not just the empty query form. */
  return (
    <OpenOnMount selector="button">
      <RetrievalPreview />
    </OpenOnMount>
  )
}
