"""Provider configuration tests for API-key and local-LLM routing modes."""

from backend.agent_runtime.provider import OpenAICompatibleProvider
from backend.config import Settings


def make_settings(
    *,
    llm_provider: str,
    llm_api_key: str = "",
    llm_base_url: str | None = None,
) -> Settings:
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
        banking_data_source="local",
        corebank_base_url="http://127.0.0.1:8080",
        corebank_timeout_seconds=1,
        corebank_fallback_to_local=True,
        corebank_service_token="test-corebank-service-token-at-least-32-characters",
        corebank_customer_emails={"U001": "user@example.com"},
        llm_provider=llm_provider,
        llm_model="test-model",
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        llm_timeout_seconds=1,
        llm_polish_responses=True,
        seed_demo_data=True,
    )


def test_local_provider_uses_deterministic_router_only():
    provider = OpenAICompatibleProvider(make_settings(llm_provider="local"))
    assert provider._connection_options() is None


def test_api_provider_requires_api_key():
    provider = OpenAICompatibleProvider(make_settings(llm_provider="deepseek"))
    assert provider._connection_options() is None


def test_deepseek_provider_supplies_official_base_url():
    provider = OpenAICompatibleProvider(
        make_settings(llm_provider="deepseek", llm_api_key="test-key")
    )
    assert provider._connection_options() == ("test-key", "https://api.deepseek.com")


def test_ollama_provider_can_run_without_real_api_key():
    provider = OpenAICompatibleProvider(make_settings(llm_provider="ollama"))
    assert provider._connection_options() == ("ollama", "http://127.0.0.1:11434/v1")


def test_polished_response_must_keep_existing_identifiers():
    provider = OpenAICompatibleProvider(make_settings(llm_provider="local"))
    assert (
        provider._safe_polished_response(
            "I found it — TXN1002 is failed.",
            "I found that payment, but it failed.",
        )
        is None
    )


def test_polished_response_cannot_add_new_identifiers():
    provider = OpenAICompatibleProvider(make_settings(llm_provider="local"))
    assert (
        provider._safe_polished_response(
            "I found it — TXN1002 is failed.",
            "I found it — TXN1002 failed, and TXN9999 also failed.",
        )
        is None
    )


def test_polished_response_can_make_safe_tone_change():
    provider = OpenAICompatibleProvider(make_settings(llm_provider="local"))
    assert (
        provider._safe_polished_response(
            "I found it — TXN1002 is failed.",
            "I found it — TXN1002 is marked failed.",
        )
        == "I found it — TXN1002 is marked failed."
    )


def test_polished_response_cannot_change_amount_or_status():
    provider = OpenAICompatibleProvider(make_settings(llm_provider="local"))
    grounded = "TXN1002 is failed for ₹25,000.00 and has high risk."

    assert (
        provider._safe_polished_response(
            grounded,
            "TXN1002 is successful for ₹20,000.00 and has low risk.",
        )
        is None
    )


def test_polished_response_cannot_add_fake_account_number():
    provider = OpenAICompatibleProvider(make_settings(llm_provider="local"))
    assert (
        provider._safe_polished_response(
            "Account 123456789012 has ₹2,500.00.",
            "Account 123456789012 has ₹2,500.00. Account 999999999999 is also active.",
        )
        is None
    )
