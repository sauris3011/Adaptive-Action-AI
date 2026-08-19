import { ApprovalPanel } from 'adaptive-action-copilot-ui'
import { RUN_APPROVED, RUN_AWAITING, RUN_REJECTED } from './_fixtures'

/* The approval gate. It lists what approving WILL do before it happens, and
   shows the effect ledger after a rejection too — three empty lists are how an
   operator sees that no side effect occurred, rather than trusting it. */

export function AwaitingApproval() {
  return <ApprovalPanel run={RUN_AWAITING} onResolved={() => {}} />
}

export function OverAgentLimit() {
  return (
    <ApprovalPanel
      onResolved={() => {}}
      run={{
        ...RUN_AWAITING,
        recommendation: { ...RUN_AWAITING.recommendation!, amount: 1240.0 },
      }}
    />
  )
}

export function Approved() {
  return <ApprovalPanel run={RUN_APPROVED} onResolved={() => {}} />
}

export function Rejected() {
  return <ApprovalPanel run={RUN_REJECTED} onResolved={() => {}} />
}

export function NothingToExecute() {
  return (
    <ApprovalPanel
      onResolved={() => {}}
      run={{ ...RUN_AWAITING, planned_actions: [] }}
    />
  )
}
