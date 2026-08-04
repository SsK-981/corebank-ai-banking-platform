# Architecture

## Services

CoreBank is the system of record for customers, KYC, accounts, balances, successful
transactions, failed attempts, and account activity risk signals. The FastAPI service owns
support conversations, approved FAQs, support tickets, and audit events. Streamlit is a
demo client and never talks directly to either database.

## Request lifecycle

1. Streamlit obtains a development JWT or receives an externally issued production JWT.
2. FastAPI validates the token and resolves the signed-in customer.
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
