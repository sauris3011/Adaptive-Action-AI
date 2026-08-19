import { StatsPanel } from 'adaptive-action-copilot-ui'

/* The three grounding stores side by side. Fraud flags live in the relational
   store and in no policy document — that separation is the point of the panel. */

const STATS = {
  vector: {
    collection: 'policy_corpus', chunks: 28, documents: 6,
    by_tier: {
      'Regulatory requirement': 5, 'Card network rules': 4,
      'Bank policy & SOP': 15, 'Product terms & conditions': 4,
    },
    by_document: { 'REG-E': 5, CNR: 4, BDP: 6, GRS: 5, PCT: 4, FSP: 4 },
    embedder: { backend: 'local:all-MiniLM-L6-v2', degraded: false, dimension: 384 },
    path: 'backend/data/chroma',
  },
  graph: {
    backend: 'kuzu', nodes: 50, relationships: 29,
    by_label: { Customer: 4, Account: 4, Merchant: 4, Transaction: 6, Dispute: 4, Policy: 28 },
    by_relationship: { HOLDS: 4, MADE: 6, AT: 6, RAISED: 4, SUPERSEDES: 2, REFERENCES: 6, DISTINCT_FROM: 1 },
  },
  relational: { customers: 4, accounts: 4, merchants: 4, transactions: 6, dispute_history: 4 },
  supported_uploads: ['text/markdown', 'text/plain'],
}

export function Default() {
  return <StatsPanel stats={STATS} />
}

export function DegradedEmbedder() {
  return (
    <StatsPanel
      stats={{
        ...STATS,
        vector: {
          ...STATS.vector,
          embedder: { backend: 'hashed:sha256-512', degraded: true, dimension: 512 },
        },
      }}
    />
  )
}
