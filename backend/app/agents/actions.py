"""Action workflow: what a recommendation maps to in the core-banking system.

The mapping is DETERMINISTIC. The model chose the action; it does not also get
to choose which endpoints get called with what payload. Turning an approved
`route_to_fraud_ops` into "open a case on the fraud queue and notify the
customer" is a policy decision, and policy decisions that move money belong in
code an auditor can read, not in a prompt.

Calls go over loopback HTTP to the mounted mock router (FR-26) so the workflow
gets a real status code back. A non-200 is a failed action, recorded as such -
never swallowed into a success.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings
from app.logging_setup import get_logger
from app.schemas.dispute import ActionType, Recommendation

log = get_logger("agents.actions")

TIMEOUT_S = 15.0


def _base_url() -> str:
    settings = get_settings()
    return f"http://127.0.0.1:{settings.port}/api/core-banking"


def _post(path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    # Loopback to our own process. Verification is irrelevant here (no TLS) and
    # app.tls deliberately does not apply: this never leaves the machine.
    with httpx.Client(timeout=TIMEOUT_S) as client:
        response = client.post(f"{_base_url()}{path}", json=payload)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    return response.status_code, body


def plan(recommendation: Recommendation, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Which mock endpoints an approved recommendation will hit, and with what.

    Returned before execution so the UI can show the operator exactly what
    approving will do. Nothing here performs an action.
    """
    run_id = state.get("run_id", "")
    customer_id = state.get("customer_id")
    transaction_id = state.get("transaction_id")
    triage = state.get("triage")
    reason_code = triage.reason_code.value if triage else "other"
    amount = recommendation.amount

    action = recommendation.action
    steps: list[dict[str, Any]] = []

    if action is ActionType.PROVISIONAL_CREDIT:
        steps.append({"instrument": "dispute_case", "path": "/dispute-cases", "payload": {
            "run_id": run_id, "customer_id": customer_id, "transaction_id": transaction_id,
            "reason_code": reason_code, "queue": "disputes", "amount": amount}})
        steps.append({"instrument": "provisional_credit", "path": "/provisional-credits",
                      "payload": {
                          "run_id": run_id, "customer_id": customer_id,
                          "transaction_id": transaction_id, "amount": amount or 0.0,
                          "governing_clause": recommendation.governing_clause,
                          "deadline": recommendation.deadline}})
        steps.append({"instrument": "customer_notice", "path": "/notices", "payload": {
            "run_id": run_id, "customer_id": customer_id,
            "subject": "Provisional credit applied to your disputed transaction",
            "body": f"{recommendation.headline}\n\n{recommendation.deadline}"}})

    elif action is ActionType.GOODWILL_REFUND:
        steps.append({"instrument": "provisional_credit", "path": "/provisional-credits",
                      "payload": {
                          "run_id": run_id, "customer_id": customer_id,
                          "transaction_id": transaction_id, "amount": amount or 0.0,
                          "governing_clause": recommendation.governing_clause,
                          "deadline": recommendation.deadline}})
        steps.append({"instrument": "customer_notice", "path": "/notices", "payload": {
            "run_id": run_id, "customer_id": customer_id,
            "subject": "Goodwill credit applied",
            "body": recommendation.headline}})

    elif action is ActionType.ROUTE_TO_FRAUD_OPS:
        # No credit and no dispute-queue case: FSP-1.2 puts Fraud Operations in
        # charge, and FSP-5.1 gives them the cardholder communication. Sending a
        # disputes notice here would breach the clause the recommendation cites.
        steps.append({"instrument": "dispute_case", "path": "/dispute-cases", "payload": {
            "run_id": run_id, "customer_id": customer_id, "transaction_id": transaction_id,
            "reason_code": reason_code, "queue": "fraud_ops", "amount": amount}})

    elif action is ActionType.REQUEST_MERCHANT_CONTACT:
        steps.append({"instrument": "customer_notice", "path": "/notices", "payload": {
            "run_id": run_id, "customer_id": customer_id,
            "subject": "Please contact the merchant before we can proceed",
            "body": recommendation.headline}})

    # DECLINE and ANSWER_ONLY intentionally produce no steps.
    return steps


def execute(recommendation: Recommendation, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Run the plan. Stops at the first failure rather than pressing on."""
    results: list[dict[str, Any]] = []
    for step in plan(recommendation, state):
        status, body = _post(step["path"], step["payload"])
        reference = (
            body.get("credit_id") or body.get("cb_case_id") or body.get("notice_id") or ""
        )
        results.append({
            "instrument": step["instrument"],
            "reference": reference,
            "status_code": status,
            "idempotent": bool(body.get("idempotent")),
            "detail": body,
        })
        if status != 200:
            log.error("action_failed", instrument=step["instrument"],
                      status=status, body=body)
            break
        log.info("action_executed", instrument=step["instrument"],
                 reference=reference, status=status)
    return results
