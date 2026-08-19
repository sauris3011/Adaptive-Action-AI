import { UploadCard } from 'adaptive-action-copilot-ui'

/* Dynamic corpus ingestion. A document without a tier in its front matter is
   rejected on purpose: precedence is a property of the corpus, not a model
   judgement. */

export function Default() {
  return <UploadCard supported={['text/markdown', 'text/plain']} onChanged={() => {}} />
}

export function ManyFormats() {
  return (
    <UploadCard
      supported={['text/markdown', 'text/plain', 'application/pdf', 'text/csv']}
      onChanged={() => {}}
    />
  )
}
