# Run instructions

## Recommended: one VS Code Run button

```powershell
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Set `BANKING_DATA_SOURCE=corebank` in `.env`, open `run_app.py`, and click Run.
The launcher starts CoreBank, seeds missing demo data, starts FastAPI and Streamlit,
and opens the chatbot.

## Complete Docker stack

```powershell
Copy-Item .env.example .env
docker compose up --build
```

## URLs

- CoreBank: `http://127.0.0.1:8080`
- FastAPI docs: `http://127.0.0.1:8000/docs`
- Chatbot: `http://127.0.0.1:8501`

## Verification

```powershell
python -m pytest
python -m ruff check backend frontend tests scripts run_app.py
python -m ruff format --check backend frontend tests scripts run_app.py
python -m mypy backend

cd corebank
.\mvnw.cmd test
```

The default CoreBank direct-run database is persistent H2 under `corebank/data`.
Docker Compose uses PostgreSQL for both CoreBank and the AI service.
