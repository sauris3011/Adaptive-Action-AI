"""Prompt assembly.

Kept separate from the nodes because these are the part most likely to be tuned,
and a prompt edit should not touch control flow.

Two rules run through all of them:

* **The ladder is stated, not inferred.** Precedence is a deterministic property
  of the corpus (PRD 5.4); the model's job is to identify the contradiction and
  apply the stated rule, not to invent a ranking.
* **Evidence is rendered by GroundingContext.render()**, highest precedence
  first, so tier order is visible in the prompt itself rather than implied.
"""

from __future__ import annotations

from app.schemas.grounding import GroundingContext, SourceTier

LADDER = "\n".join(
    f"  {int(tier)}. {tier.label}" for tier in sorted(SourceTier, key=int)
)

TRIAGE_SYSTEM = """You extract structured intent from a bank dispute agent's request.

Extract only what the text actually states. Do not infer a transaction id, a
customer id or an amount that is not there - a wrong id sends the whole pipeline
to the wrong record, which is worse than a null.

The retrieval_query field matters most: write the substantive policy question,
not the customer's story. "Provisional credit timing for a premium cardholder
dispute" retrieves well; "customer is angry about a charge" does not."""

RECONCILE_SYSTEM = f"""You reconcile evidence from a bank's policy corpus, its knowledge graph and
its systems of record.

PRECEDENCE LADDER (lower number wins):
{LADDER}

OVERRIDE RULE: where a lower-precedence source is MORE FAVOURABLE TO THE CUSTOMER
and breaches no higher tier, the more favourable term binds. A regulatory maximum
is a ceiling, not a target: a contractual promise to act faster is enforceable and
therefore governs.

Your task, in order:

1. Identify every material contradiction across the evidence.
2. For each, decide which clause governs by applying the ladder and the override
   rule. The tier is given to you in the evidence - do not re-rank it.
3. Distinguish a TRUE conflict from an APPARENT one. Two clauses that govern
   DIFFERENT INSTRUMENTS or different scopes do not conflict, even when their
   requirements differ. Set is_true_conflict to false and explain the distinction.
4. Treat facts from a RECORD source as authoritative about the world. A document
   cannot override what the system of record says is true; it can only tell you
   what to do about it. Where a record fact triggers a routing or handling rule,
   that rule applies regardless of what the request says.

Report only contradictions the evidence actually supports. Inventing a conflict is
as damaging as missing one."""

RECOMMEND_SYSTEM = """You produce a grounded recommendation for a bank dispute agent.

Rules:

- Cite clause ids and record refs exactly as they appear in the evidence. Never
  cite a clause that is not in the evidence.
- governing_clause is the single clause that decides the outcome. If reconciliation
  found a governing clause, use it.
- Always state the applicable deadline concretely. Where the deadline comes from a
  clause, say which.
- requires_approval is true for anything that moves money or opens a case.
- Confidence reflects the evidence, not your fluency. Lower it when the evidence is
  thin, when sources conflict unresolved, or when a needed fact is missing.
- If an attachment was supplied but not interpreted, say so in caveats rather than
  reasoning as though you had read it.
- Recommend only what the evidence supports. "Escalate" or "decline" is a valid
  outcome; a confident answer that outruns the evidence is not."""

QA_SYSTEM = """You answer a policy question for a bank dispute agent (US-5). No case is opened.

Answer only from the evidence, cite the clause ids you rely on, and say plainly when
the evidence does not settle the question. Where sources disagree, state which one
governs and why. Use action "answer_only" and requires_approval false."""


def _attachment_note(attachments: list[str]) -> str:
    if not attachments:
        return ""
    return (
        "\n\nATTACHMENTS SUPPLIED BUT NOT INTERPRETED: "
        + ", ".join(attachments)
        + "\nThese are stored and referenceable, but their contents were NOT read. Do not "
          "reason about what they contain; note the limitation in caveats."
    )


def triage_user(text: str) -> str:
    return f"Agent request:\n\n{text}"


def reconcile_user(question: str, grounding: GroundingContext) -> str:
    return (
        f"QUESTION UNDER CONSIDERATION:\n{question}\n\n"
        f"EVIDENCE (highest precedence first):\n\n{grounding.render()}"
    )


def recommend_user(
    question: str,
    grounding: GroundingContext,
    reconciliation_summary: str,
    attachments: list[str] | None = None,
) -> str:
    return (
        f"REQUEST:\n{question}\n\n"
        f"RECONCILIATION:\n{reconciliation_summary}\n\n"
        f"EVIDENCE (highest precedence first):\n\n{grounding.render()}"
        f"{_attachment_note(attachments or [])}"
    )


def render_reconciliation(conflicts: list, notes: str) -> str:
    """Compact the reconciliation for the recommend prompt.

    Passing the full object back as JSON invites the model to restate it; a
    prose summary keeps the recommendation focused on the decision.
    """
    if not conflicts:
        return f"No contradictions detected. {notes}".strip()
    lines = []
    for conflict in conflicts:
        kind = "CONFLICT" if conflict.is_true_conflict else "APPARENT CONFLICT ONLY"
        superseded = ", ".join(conflict.superseded_clauses) or "none"
        lines.append(
            f"- {kind}: {conflict.description}\n"
            f"  Governing: {conflict.governing_clause} (tier {int(conflict.governing_tier)}, "
            f"{conflict.governing_tier.label})\n"
            f"  Not governing: {superseded}\n"
            f"  Basis: {conflict.resolution_basis}"
        )
    return "\n".join(lines) + (f"\n\nNotes: {notes}" if notes else "")
