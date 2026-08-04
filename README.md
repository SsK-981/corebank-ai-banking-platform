# AI Banking Support Platform

A grounded banking-support assistant that connects a Spring Boot CoreBank service with
a FastAPI agent, PostgreSQL-backed state, deterministic banking tools, and a Streamlit
demo UI.

This is a production-oriented portfolio implementation using synthetic banking data.
The LLM can help classify and phrase requests, but it cannot directly read databases,
modify balances, or rewrite financial facts returned by CoreBank.

## Screenshots

The chatbot answers from live CoreBank transaction history, including failed attempts.

![Grounded transaction history](docs/screenshots/chatbot-corebank-history.png)

CoreBank separates the customer portal from the operations console.

![CoreBank portal](docs/screenshots/corebank-portal.png)

Operations staff can review customers, accounts, KYC state, and account activity
risk signals.

![CoreBank KYC operations](docs/screenshots/corebank-admin-kyc.png)

## Architecture

```mermaid
flowchart LR
    C["Customer"] --> UI["Streamlit UI"]
    UI -->|"JWT"| AI["FastAPI agent"]
    AI --> R["Intent router"]
    R -. "optional" .-> LLM["OpenAI-compatible LLM"]
    R --> T["Approved tools"]
    T -->|"service token"| CB["Spring Boot CoreBank"]
    T --> FAQ["Approved policies"]
    T --> ADB["Agent database"]
    CB --> CDB["CoreBank database"]
```

CoreBank is the system of record for customer identity, KYC, accounts, balances,
transactions, failed transaction attempts, and account activity risk. The agent owns
conversations, support tickets, approved policies, and audit events.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Engineering guarantees

- **Grounded financial responses:** account facts are fetched through CoreBank tools
  and rendered with deterministic templates.
- **Customer-scoped access:** FastAPI validates JWTs, and CoreBank rechecks ownership
  before returning account data to the AI service.
- **Banking integrity controls:** money uses decimal types, transfers are transactional,
  failed attempts are persisted, and optimistic locking prevents silent balance loss.

## Tech stack

| Area | Stack |
|---|---|
| Core banking | Java 21, Spring Boot, Spring Security, JPA, Flyway |
| Agent API | Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic |
| UI | Streamlit |
| Data | PostgreSQL in Docker Compose; local SQLite/H2 demo modes |
| Quality | Pytest, JUnit, Ruff, mypy, GitHub Actions |

## Quick start

Requirements:

- Docker Desktop with Compose
- Or Python 3.12 and JDK 21 for direct local development

Run the full stack:

```bash
cp .env.example .env
docker compose up --build
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open:

- Chatbot UI: <http://127.0.0.1:8501>
- CoreBank portal: <http://127.0.0.1:8080>
- FastAPI docs: <http://127.0.0.1:8000/docs>
- CoreBank API docs: <http://127.0.0.1:8080/swagger-ui.html>

The Compose stack starts two PostgreSQL databases, CoreBank, demo seeding, FastAPI,
Alembic migrations, and Streamlit.

## Example requests

Select demo customer `U002` in the chatbot and ask:

1. `What is my account balance?`
2. `Show my transactions.`
3. `Why did my failed withdrawal fail?`
4. `What is my KYC status?`
5. `Review account activity risk.`
6. `Open a support case for the failed payment.`
7. `Show me U001's account balance.`

The final request should be denied because it asks for another customer's record.

Demo script: [docs/DEMO.md](docs/DEMO.md)

## LLM modes

The application runs without an external model through its deterministic router.

OpenAI-compatible providers can be enabled for intent routing and tone:

```dotenv
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-flash
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.deepseek.com
LLM_POLISH_RESPONSES=true
```

Provider failures, invalid structured output, and malformed responses fall back to
local routing. Financial facts still bypass model polishing.

## Verification

Python checks:

```powershell
python -m ruff check backend frontend tests scripts run_app.py
python -m ruff format --check backend frontend tests scripts run_app.py
python -m mypy backend
python -m pytest
```

CoreBank checks:

```powershell
cd corebank
.\mvnw.cmd test
```

Current automated coverage in the repository:

- 60 Python unit/API tests
- 19 Spring Boot integration tests
- 1 live chatbot-to-CoreBank contract test
- Alembic and Flyway migration checks in CI
- Docker builds for backend, frontend, and CoreBank images

## Security boundaries

- Local demo credentials are only for synthetic data.
- Production mode rejects demo seeding and disabled authentication.
- The AI service uses a service credential, not customer banking passwords.
- Messages are redacted before optional LLM routing.
- Conversation access is owner-scoped and privileged actions are audited.
- A portfolio project is not a licensed bank, compliance program, or validated fraud
  model.

Security notes: [SECURITY.md](SECURITY.md)
Threat model: [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)

## Known limitations

- Demo identity selection still uses fixed local users.
- Account activity risk is rule-based and should not be described as fraud detection.
- PostgreSQL-backed concurrency tests should be expanded beyond the current local test
  coverage.
- Money movement still needs explicit idempotency keys and ledger-style postings before
  it can model retry-safe banking transfers.
- A reproducible agent evaluation dataset should be added for intent accuracy, tool
  selection, refusal behavior, and provider-failure recovery.

## Repository layout

```text
corebank/       Spring Boot banking system of record
backend/        FastAPI agent, tools, security, persistence
frontend/       Streamlit demo UI
alembic/        Agent database migrations
scripts/        CoreBank demo seeding
tests/          Python API, unit, and live integration tests
docs/           Architecture, demo, and threat-model notes
compose.yaml    Complete local stack
run_app.py      Local launcher for direct development
```

## License

MIT - see [LICENSE](LICENSE).
