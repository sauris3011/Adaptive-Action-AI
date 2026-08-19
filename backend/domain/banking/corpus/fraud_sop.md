---
doc_id: FSP
title: Fraud Operations Standard Operating Procedure
tier: 3
authority: Internal — Fraud Operations
effective: 2025-04-01
---

## FSP-1.2 — Mandatory routing on a fraud-engine flag

Any transaction carrying a fraud-engine flag is routed to Fraud Operations. Fraud Operations owns the
case from that point. The standard dispute intake path is not used for these transactions, and no
provisional credit is issued through the disputes queue while Fraud Operations holds the case.

This routing requirement takes effect on the presence of the flag in the transaction record. It does
not depend on what the cardholder reports, and it applies whether or not a dispute has already been
opened under BDP-2.1.

## FSP-2.4 — Fraud engine flag definition

A fraud-engine flag is set by the real-time scoring engine at authorisation. It is recorded on the
transaction record. It is not published in any policy document and is not visible from the case notes
alone.

## FSP-3.1 — Card handling

Where a fraud-engine flag is confirmed, the card is blocked and reissued before the case is closed.

## FSP-5.1 — Cardholder communication

Fraud Operations issues its own cardholder notice. Disputes agents do not send dispute
correspondence for a transaction routed under FSP-1.2.
