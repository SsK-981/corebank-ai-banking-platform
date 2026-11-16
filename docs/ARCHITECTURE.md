# Architecture

## Services

CoreBank is the system of record for customers, KYC, accounts, balances, successful
transactions, failed attempts, and account activity risk signals. The FastAPI service owns
support conversations, approved FAQs, support tickets, and audit events. Streamlit is a
demo client and never talks directly to either database.

## Request lifecycle

1. The CoreBank customer portal sends Help requests to Spring on the same origin.
   Spring uses the authenticated customer and supplies the identity and service
   credential server-side. FastAPI maps that email to a seeded customer ID.
2. For standalone Streamlit, FastAPI validates a development or externally issued JWT.
3. The local router handles safety and obvious intents before optional LLM routing.
4. The orchestrator selects a narrowly scoped tool.
5. CoreBank authenticates the AI service and independently verifies customer ownership.
6. A deterministic template renders financial facts; DeepSeek cannot rewrite it.
7. The conversation, source metadata, request ID, and audit event are persisted.

## Data ownership

| Data | Owner |
|---|---|
| Customer profile and KYC | CoreBank |
| Accounts and balances | CoreBank |
| Posted and failed transactions | CoreBank |
| Account activity risk signals | CoreBank |
| Conversations and messages | AI agent database |
| Approved policies | AI agent database |
| Support tickets and audit events | AI agent database |

## Failure behavior

- LLM unavailable: deterministic router continues.
- CoreBank unavailable: integrated mode returns an unavailable response; it does not
  silently substitute demo balances.
- Invalid/unknown transaction: the agent asks the customer to verify the reference.
- Concurrent balance update: CoreBank returns a conflict instead of silently losing an
  update.
- High account activity risk: the system recommends manual review and does not
  auto-approve.

## Customer transfer retries

The portal creates one idempotency key when a customer confirms a transfer.
CoreBank locks the source and destination rows in ascending account-ID order.
It checks funds under those locks and commits the result in the same transaction
as the debit and credit or the insufficient-funds attempt. A repeat with the
same key and transfer details receives that result. Reusing the key with changed
details returns a conflict. The customer receipt returns a masked recipient
name, and the portal refreshes the latest balance after receiving the receipt.

The portal keeps one unresolved transfer per customer in the current tab.
If a response is lost, **Retry transfer** resends its original request. The
same retry is safe if the first request already committed.
