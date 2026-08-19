import { EvidencePanel } from 'adaptive-action-copilot-ui'
import { EVIDENCE } from './_fixtures'
import { OpenOnMount } from './_open'

/* Collapsed by default in the product — the reviewer reads the recommendation,
   the analyst opens the evidence. The panel owns its open state internally, so
   the expanded cards click the real header control on mount. */

export function Collapsed() {
  return <EvidencePanel evidence={EVIDENCE} />
}

export function Expanded() {
  return (
    <OpenOnMount>
      <EvidencePanel evidence={EVIDENCE} />
    </OpenOnMount>
  )
}

export function PolicyOnly() {
  return (
    <OpenOnMount>
      <EvidencePanel evidence={EVIDENCE.filter((e) => e.kind === 'policy')} />
    </OpenOnMount>
  )
}
