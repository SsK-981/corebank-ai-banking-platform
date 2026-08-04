"""Explainable, rule-based transaction risk scoring."""


def score_transaction(amount: float, failed_attempts: int, kyc_status: str) -> dict:
    """Return a deterministic risk level and all matching reasons."""
    high_risk_reasons: list[str] = []

    if amount > 20_000:
        high_risk_reasons.append("Transaction amount is above INR 20,000")
    if failed_attempts >= 3:
        high_risk_reasons.append("Transaction has 3 or more failed attempts")
    if kyc_status.lower() == "pending" and amount > 5_000:
        high_risk_reasons.append("KYC is pending for a transaction above INR 5,000")

    if high_risk_reasons:
        return {"risk_level": "high", "reasons": high_risk_reasons}
    if 5_000 <= amount <= 20_000:
        return {
            "risk_level": "medium",
            "reasons": ["Transaction amount is between INR 5,000 and INR 20,000"],
        }
    return {
        "risk_level": "low",
        "reasons": ["No high- or medium-risk rule was triggered"],
    }
