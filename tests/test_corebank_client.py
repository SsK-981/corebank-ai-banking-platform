"""Tests for the Spring Boot CoreBank API adapter."""

from backend.config import Settings
from backend.corebank_client import CoreBankAccessDenied, CoreBankClient


def make_settings() -> Settings:
    return Settings(
        app_name="test",
        app_env="development",
        database_url="sqlite:///:memory:",
        cors_origins=("http://127.0.0.1:8501",),
        auth_mode="development",
        jwt_secret="x" * 32,
        jwt_algorithm="HS256",
        jwt_issuer=None,
        jwt_audience=None,
        jwt_jwks_url=None,
        access_token_minutes=60,
        banking_data_source="corebank",
        corebank_base_url="http://corebank.test",
        corebank_timeout_seconds=1,
        corebank_fallback_to_local=False,
        corebank_service_token="test-corebank-service-token-at-least-32-characters",
        corebank_customer_emails={"U002": "amit@example.com"},
        llm_provider="local",
        llm_model="test-model",
        llm_base_url=None,
        llm_api_key="",
        llm_timeout_seconds=1,
        llm_polish_responses=True,
        seed_demo_data=True,
    )


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.content = b"{}" if payload is not None else b""

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/internal/ai/customers/amit%40example.com/profile"):
            return FakeResponse(
                {
                    "id": 9,
                    "fullName": "Amit Verma",
                    "email": "amit@example.com",
                    "role": "CUSTOMER",
                    "kycStatus": "VERIFIED",
                }
            )
        if url.endswith("/internal/ai/customers/amit%40example.com/accounts"):
            return FakeResponse(
                {
                    "content": [
                        {
                            "accountId": 42,
                            "accountNumber": "123456789012",
                            "holderName": "Amit Verma",
                            "balance": 2500.75,
                            "active": True,
                            "ownerEmail": "amit@example.com",
                        }
                    ]
                }
            )
        if url.endswith("/internal/ai/customers/amit%40example.com/accounts/42/transactions"):
            return FakeResponse(
                {
                    "content": [
                        {
                            "id": 7,
                            "type": "TRANSFER_SENT",
                            "amount": 500,
                            "timestamp": "2026-08-04T10:00:00",
                            "referenceNumber": "TXNABC123",
                            "description": "Transfer TXNABC123 to account 999",
                            "status": "FAILED",
                            "failureReason": "Insufficient balance",
                        }
                    ]
                }
            )
        if url.endswith("/internal/ai/customers/amit%40example.com/accounts/42/risk-insights"):
            return FakeResponse(
                {
                    "accountId": 42,
                    "accountNumber": "123456789012",
                    "riskLevel": "MEDIUM",
                    "riskScore": 40,
                    "currentBalance": 2500.75,
                    "totalCredits": 5000,
                    "totalDebits": 2500,
                    "largestTransaction": 1000,
                    "transactionCount": 4,
                    "signals": [
                        {
                            "code": "BALANCE_DRAIN",
                            "title": "High debit pressure",
                            "detail": "Debits are close to credits.",
                            "points": 28,
                        }
                    ],
                    "recommendation": "Monitor upcoming activity.",
                }
            )
        return FakeResponse({"message": "not found"}, status_code=404)


def test_corebank_client_lists_customer_transactions_with_service_token():
    client = CoreBankClient(make_settings())
    fake_session = FakeSession()
    client.session = fake_session

    result = client.list_transactions("U002")

    assert result["source"] == "corebank"
    assert result["transactions"][0]["transaction_id"] == "TXNABC123"
    assert result["transactions"][0]["account_id"] == 42
    assert result["transactions"][0]["status"] == "failed"
    assert result["transactions"][0]["failure_reason"] == "Insufficient balance"
    assert fake_session.calls[0][2]["headers"]["X-CoreBank-Service-Token"].startswith(
        "test-corebank"
    )


def test_corebank_client_returns_account_summary():
    client = CoreBankClient(make_settings())
    client.session = FakeSession()

    result = client.account_summary("U002")

    assert result["profile"]["full_name"] == "Amit Verma"
    assert result["profile"]["kyc_status"] == "verified"
    assert result["total_balance"] == 2500.75
    assert result["active_accounts"] == 1


def test_corebank_client_returns_risk_insights_for_transaction():
    client = CoreBankClient(make_settings())
    client.session = FakeSession()

    result = client.risk_insights("U002", transaction_id="TXNABC123")

    assert result["risk_level"] == "medium"
    assert result["risk_score"] == 40
    assert "High debit pressure" in result["reasons"][0]


def test_corebank_client_requires_mapped_customer():
    client = CoreBankClient(make_settings())

    try:
        client.list_accounts("U999")
    except CoreBankAccessDenied as exc:
        assert "No CoreBank customer mapping" in str(exc)
    else:
        raise AssertionError("Expected CoreBankAccessDenied")
