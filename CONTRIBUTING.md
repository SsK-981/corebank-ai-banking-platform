# Contributing

1. Create a focused branch.
2. Never add real customer data or secrets.
3. Add tests for behavior changes.
4. Run Python and Java verification before opening a pull request.

```powershell
python -m pytest
python -m ruff check backend frontend tests scripts run_app.py
python -m mypy backend
cd corebank
.\mvnw.cmd test
```

Changes to financial facts, authorization, migrations, or money movement require an
integration test and a short explanation of failure behavior.
