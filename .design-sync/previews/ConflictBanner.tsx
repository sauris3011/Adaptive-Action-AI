import { ConflictBanner } from 'adaptive-action-copilot-ui'
import { CONFLICTS } from './_fixtures'

/* Reconciliation made visible. The losing source is shown beside the governing
   one on purpose — stating only the winner is indistinguishable from ordinary
   RAG right up until it is wrong. */

export function NoConflicts() {
  return <ConflictBanner conflicts={[]} notes="The retrieved sources agree on the governing rule." />
}

export function TrueConflict() {
  return (
    <ConflictBanner
      conflicts={[CONFLICTS[0]]}
      notes="Precedence ladder applied: tier 1 (regulatory) over tier 3 (bank policy)."
    />
  )
}

export function ApparentConflictOnly() {
  return <ConflictBanner conflicts={[CONFLICTS[1]]} notes="" />
}

export function Both() {
  return (
    <ConflictBanner
      conflicts={CONFLICTS}
      notes="Two contradictions surfaced during reconciliation; one resolved as a genuine precedence question, one as a category error."
    />
  )
}
