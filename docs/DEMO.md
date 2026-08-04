# 90-second demo

## Setup

```powershell
docker compose up --build
```

Open CoreBank at `http://127.0.0.1:8080` and the chatbot at
`http://127.0.0.1:8501`.

## Script

1. **Architecture:** “CoreBank is the Java system of record. FastAPI is the grounded AI
   orchestration layer. The model never receives database access.”
2. **Live balance:** select U002 and ask `What is my account balance?`.
3. **Live history:** ask `Show my transactions.` Point out the persisted failed attempt.
4. **KYC:** ask `What is my KYC status?`. Change it in the CoreBank admin portal and ask
   again to demonstrate live integration.
5. **Risk:** ask `Is my account risky?` and expand agent activity to show the tool used.
6. **Authorization:** ask for `U001` while signed in as U002; the request is refused.
7. **Escalation:** ask `Open a support case for this failed payment.` Show the ticket ID.
8. **Grounding:** explain that tool-backed responses skip LLM rewriting, while greetings
   can still use DeepSeek for natural tone.

## Suggested interviewer questions

- Why is `@Transactional` insufficient by itself for concurrent withdrawals?
- Why does the AI service use a service credential instead of customer passwords?
- What happens when DeepSeek is unavailable?
- Which database owns KYC and transaction status?
- How would production OIDC, mTLS, rate limiting, and monitoring be added?
