"""Boundary tests for deterministic risk rules."""

from backend.risk_engine import score_transaction


def test_low_risk_transaction():
    assert score_transaction(4999, 0, "verified")["risk_level"] == "low"


def test_medium_risk_boundaries():
    assert score_transaction(5000, 0, "verified")["risk_level"] == "medium"
    assert score_transaction(20000, 0, "verified")["risk_level"] == "medium"


def test_amount_above_limit_is_high():
    result = score_transaction(20001, 0, "verified")
    assert result["risk_level"] == "high"
    assert "above INR 20,000" in result["reasons"][0]


def test_repeated_failures_are_high():
    assert score_transaction(100, 3, "verified")["risk_level"] == "high"


def test_pending_kyc_above_limit_is_high():
    assert score_transaction(5001, 0, "pending")["risk_level"] == "high"
