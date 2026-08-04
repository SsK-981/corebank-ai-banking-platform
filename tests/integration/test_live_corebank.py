"""Cross-service contract test, enabled by RUN_LIVE_COREBANK_TESTS=1."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend.agent_runtime.orchestrator import FintechAgent
from backend.config import get_settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_COREBANK_TESTS") != "1",
    reason="requires a running and seeded CoreBank service",
)


def test_chatbot_reads_live_corebank_kyc_balance_and_failed_transaction(monkeypatch):
    monkeypatch.setenv("BANKING_DATA_SOURCE", "corebank")
    monkeypatch.setenv("COREBANK_BASE_URL", os.getenv("COREBANK_BASE_URL", "http://127.0.0.1:8080"))
    monkeypatch.setenv(
        "COREBANK_SERVICE_TOKEN",
        os.getenv("COREBANK_SERVICE_TOKEN", "local-corebank-service-token-change-me"),
    )
    monkeypatch.setenv("COREBANK_FALLBACK_TO_LOCAL", "false")
    get_settings.cache_clear()

    from backend import main

    main.agent = FintechAgent()
    try:
        with TestClient(main.app) as client:
            token_response = client.post(
                "/auth/dev-token",
                json={"user_id": "U002", "role": "customer"},
            )
            token_response.raise_for_status()
            headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}

            kyc = client.post("/chat", json={"message": "What is my KYC status?"}, headers=headers)
            kyc.raise_for_status()
            assert "pending" in kyc.json()["response"].lower()
            assert "check_kyc_status" in kyc.json()["tools_used"]

            history = client.post(
                "/chat",
                json={"message": "Show my transactions"},
                headers=headers,
            )
            history.raise_for_status()
            assert "failed" in history.json()["response"].lower()
            assert "list_user_transactions" in history.json()["tools_used"]

            balance = client.post(
                "/chat",
                json={"message": "What is my account balance?"},
                headers=headers,
            )
            balance.raise_for_status()
            assert "get_account_summary" in balance.json()["tools_used"]
            assert "₹" in balance.json()["response"]
    finally:
        get_settings.cache_clear()
