"""Isolated application configuration for integration tests."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DB = Path(__file__).resolve().parent / ".test_fintech.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["AUTH_MODE"] = "development"
os.environ["JWT_SECRET"] = "test-secret-that-is-definitely-at-least-32-characters"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["BANKING_DATA_SOURCE"] = "local"
os.environ["LLM_PROVIDER"] = "local"
os.environ.pop("LLM_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)

from backend.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def get_token(client: TestClient, role: str, user_id: str | None = None) -> str:
    response = client.post("/auth/dev-token", json={"role": role, "user_id": user_id})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture()
def u001_headers(client):
    token = get_token(client, "customer", "U001")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def u002_headers(client):
    token = get_token(client, "customer", "U002")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client):
    token = get_token(client, "admin")
    return {"Authorization": f"Bearer {token}"}
