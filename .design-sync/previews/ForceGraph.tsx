import { ForceGraph } from 'adaptive-action-copilot-ui'

/* The entity subgraph around a disputed transaction. Deliberately separate from
   the policy subgraph — entity facts come from records, policy edges from the
   corpus, and mixing them would hide which one decided an outcome. */

const NODES = [
  { id: 'CUST-1042', label: 'Customer', caption: 'A. Sharma', distance: 2, props: { customer_id: 'CUST-1042', segment: 'premium' } },
  { id: 'ACC-5501', label: 'Account', caption: 'Signature Premium Card', distance: 1, props: { account_id: 'ACC-5501' } },
  { id: 'TXN-9002', label: 'Transaction', caption: 'TXN-9002 - 240.00 USD', distance: 0, props: { amount: 240.0, fraud_flag: true, channel: 'card_present' } },
  { id: 'MER-77', label: 'Merchant', caption: 'Northwind Electronics', distance: 1, props: { merchant_id: 'MER-77', mcc: '5732' } },
  { id: 'DSP-1183', label: 'Dispute', caption: 'unauthorised', distance: 1, props: { dispute_id: 'DSP-1183', reason_code: 'unauthorised' } },
  { id: 'TXN-9003', label: 'Transaction', caption: 'TXN-9003 - 38.50 USD', distance: 2, props: { amount: 38.5, fraud_flag: false } },
]

const LINKS = [
  { source: 'CUST-1042', target: 'ACC-5501', label: 'HOLDS' },
  { source: 'ACC-5501', target: 'TXN-9002', label: 'MADE' },
  { source: 'TXN-9002', target: 'MER-77', label: 'AT' },
  { source: 'CUST-1042', target: 'DSP-1183', label: 'RAISED' },
  { source: 'DSP-1183', target: 'TXN-9002', label: 'REFERENCES' },
  { source: 'ACC-5501', target: 'TXN-9003', label: 'MADE' },
  { source: 'TXN-9003', target: 'MER-77', label: 'AT' },
]

const VIEW = { root: 'TXN-9002', found: true, hops: 2, nodes: NODES, links: LINKS, truncated: false }

export function Default() {
  return <ForceGraph view={VIEW} onSelect={() => {}} selectedId={null} />
}

export function NodeSelected() {
  return <ForceGraph view={VIEW} onSelect={() => {}} selectedId="TXN-9002" />
}

export function EmptyGraph() {
  return (
    <ForceGraph
      view={{ root: null, found: false, hops: null, nodes: [], links: [], truncated: false }}
      onSelect={() => {}}
      selectedId={null}
    />
  )
}
