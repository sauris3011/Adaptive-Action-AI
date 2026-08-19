"""Per-case scoring against the labelled eval set (PRD 9.1).

Scoring is deliberately strict and mechanical. Every judgement here is a set
membership test or a substring match against a label written from the corpus -
there is no model in this file. An eval that asks an LLM whether the LLM was
right measures agreement, not correctness, and would make the headline metric
unfalsifiable.

The one place judgement was needed - which alternative actions still count as
correct - is encoded in the eval set as `acceptable_actions`, so it is visible
and reviewable rather than buried in scoring logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# A deadline field that says one of these is not a stated deadline.
_NO_DEADLINE = ("none applicable", "not applicable", "no deadline", "n/a", "none")


@dataclass
class CaseScore:
    case_id: str
    conflict_id: str | None = None
    ok_action: bool = False
    ok_clause: bool = False
    ok_citation_any: bool = False
    ok_citation_correct: bool = False
    ok_conflict: bool | None = None       # None when the case expects no conflict
    ok_deadline: bool | None = None       # None when no deadline applies
    automated: bool = False
    grounded: bool = False
    latency_ms: int = 0
    produced_action: str = ""
    produced_clause: str = ""
    citations: list[str] = field(default_factory=list)
    error: str | None = None
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """A case passes only if every dimension it is scored on passes."""
        if self.error:
            return False
        checks = [self.ok_action, self.ok_clause, self.ok_citation_correct]
        if self.ok_conflict is not None:
            checks.append(self.ok_conflict)
        if self.ok_deadline is not None:
            checks.append(self.ok_deadline)
        return all(checks)


def _deadline_stated(deadline: str) -> bool:
    text = (deadline or "").strip().lower()
    return bool(text) and not any(text.startswith(marker) for marker in _NO_DEADLINE)


def _conflict_matches(expected: dict[str, Any], conflicts: list[dict[str, Any]]) -> bool:
    """Found when SOME reported conflict names an accepted governing clause and
    agrees on whether the contradiction is real.

    `governing_any` exists for APPARENT conflicts, where the pair is symmetric:
    two clauses govern different instruments, and which one is "governing"
    depends on which instrument the reader has in mind. Successive runs named
    opposite sides of C2 while classifying it correctly as apparent both times,
    so pinning one side would score a correct answer as wrong half the time. The
    substantive check - true conflict versus apparent - stays strict.

    Extra conflicts are not penalised: retrieving more of the corpus legitimately
    surfaces more contradictions, and punishing that would train the eval toward
    narrower retrieval.
    """
    accepted = expected.get("governing_any") or [expected["governing"]]
    for conflict in conflicts:
        if conflict.get("governing_clause") not in accepted:
            continue
        if bool(conflict.get("is_true_conflict")) != bool(expected["is_true"]):
            continue
        return True
    return False


def score_case(case: dict[str, Any], run: dict[str, Any] | None, error: str | None,
               latency_ms: int) -> CaseScore:
    result = CaseScore(case_id=case["id"], conflict_id=case.get("conflict_id"),
                       latency_ms=latency_ms, error=error)
    if error or not run:
        result.failures.append(f"run failed: {error}")
        return result

    recommendation = run.get("recommendation") or {}
    reconciliation = run.get("reconciliation") or {}
    evidence = run.get("evidence") or []

    result.grounded = bool(evidence)
    result.produced_action = recommendation.get("action", "")
    result.produced_clause = recommendation.get("governing_clause", "")
    result.citations = list(recommendation.get("citations") or [])

    result.ok_action = result.produced_action in case["acceptable_actions"]
    if not result.ok_action:
        result.failures.append(
            f"action {result.produced_action!r} not in {case['acceptable_actions']}")

    result.ok_clause = result.produced_clause in case["acceptable_clauses"]
    if not result.ok_clause:
        result.failures.append(
            f"clause {result.produced_clause!r} not in {case['acceptable_clauses']}")

    # FR-5 has two halves: cited SOMETHING, and cited the RIGHT thing.
    result.ok_citation_any = bool(result.citations)
    missing = [ref for ref in case.get("must_cite", []) if ref not in result.citations]
    # must_cite_any is for cases where two clauses are both legitimately
    # citable - typically where a regulation and a bank policy state the same
    # rule at different tiers. Requiring one specific side would score a correct
    # answer as wrong.
    any_of = case.get("must_cite_any") or []
    satisfied_any = not any_of or any(ref in result.citations for ref in any_of)
    result.ok_citation_correct = result.ok_citation_any and not missing and satisfied_any
    if missing:
        result.failures.append(f"missing citations {missing}")
    if not satisfied_any:
        result.failures.append(f"cited none of {any_of}")

    expected_conflict = case.get("conflict")
    if expected_conflict:
        result.ok_conflict = _conflict_matches(
            expected_conflict, reconciliation.get("conflicts") or [])
        if not result.ok_conflict:
            found = [(c.get("governing_clause"), c.get("is_true_conflict"))
                     for c in reconciliation.get("conflicts") or []]
            result.failures.append(
                f"conflict {expected_conflict['governing']} "
                f"(true={expected_conflict['is_true']}) not detected; found {found}")

    if case.get("deadline_required"):
        deadline = recommendation.get("deadline", "")
        stated = _deadline_stated(deadline)
        wanted = case.get("deadline_must_mention") or []
        mentions = all(token.lower() in deadline.lower() for token in wanted)
        result.ok_deadline = stated and mentions
        if not result.ok_deadline:
            result.failures.append(
                f"deadline {deadline!r} missing or does not mention {wanted}")

    # Automation rate: resolved without escalating to a human for further work.
    result.automated = result.ok_action and result.produced_action != "decline"
    return result
