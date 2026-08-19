import { RecommendationCard } from 'adaptive-action-copilot-ui'
import { EVIDENCE, RECOMMENDATION } from './_fixtures'

/* The product's primary surface: what the copilot decided, what governs it,
   and every citation resolved back to retrieved evidence. */

export function Default() {
  return <RecommendationCard recommendation={RECOMMENDATION} evidence={EVIDENCE} elapsedMs={8420} />
}

export function LowConfidence() {
  return (
    <RecommendationCard
      elapsedMs={12960}
      evidence={EVIDENCE}
      recommendation={{
        ...RECOMMENDATION,
        action: 'request_merchant_contact',
        headline: 'Ask the cardholder to contact the merchant before raising a chargeback',
        confidence: 0.41,
        amount: 38.5,
        governing_clause: 'CNR-11.4',
        deadline: '2026-09-02 (15 days, card network window)',
        rationale:
          'The dispute reads as goods-not-received rather than unauthorised use. Card network rules require a '
          + 'documented merchant contact attempt before a chargeback is eligible under this reason code.',
        caveats:
          'Confidence is low: the description does not state whether delivery was attempted. Confirm with the '
          + 'cardholder before relying on this routing.',
      }}
    />
  )
}

export function UncitedSource() {
  return (
    <RecommendationCard
      elapsedMs={7310}
      evidence={EVIDENCE.slice(0, 2)}
      recommendation={{
        ...RECOMMENDATION,
        citations: ['REG-E-2', 'BDP-3.4', 'FSP-9.9'],
        headline: 'Issue provisional credit within the regulatory window',
        action: 'provisional_credit',
        rationale:
          'The investigation will not conclude inside the 10 business day window, so REG-E-2 obliges a '
          + 'provisional credit of the full disputed amount. At 240.00 USD this sits below the BDP-3.4 agent '
          + 'limit and can be approved without a Team Lead.',
        caveats:
          'One citation (FSP-9.9) is not present in the retrieved evidence and is flagged below rather than '
          + 'assumed correct.',
      }}
    />
  )
}

export function AnswerOnly() {
  return (
    <RecommendationCard
      elapsedMs={3120}
      evidence={EVIDENCE.slice(0, 3)}
      recommendation={{
        ...RECOMMENDATION,
        action: 'answer_only',
        headline: 'Provisional credit is due within 10 business days of notice',
        amount: null,
        requires_approval: false,
        confidence: 0.94,
        caveats: '',
        citations: ['REG-E-2'],
        rationale:
          'Regulation E sets the outer bound: if the investigation is not complete within 10 business days of '
          + 'notice, the disputed amount must be provisionally credited pending the outcome. This is an answer to '
          + 'a policy question, so no action is planned and nothing requires approval.',
      }}
    />
  )
}
