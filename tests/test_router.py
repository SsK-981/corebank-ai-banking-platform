"""Golden routing examples for common paraphrases."""

import pytest

from backend.agent_runtime.plan import Intent
from backend.agent_runtime.router import RuleRouter


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Where is payment TXN1003?", Intent.TRANSACTION_STATUS),
        ("Where is payment TXNABCD1234?", Intent.TRANSACTION_STATUS),
        ("What is my account balance?", Intent.ACCOUNT_SUMMARY),
        ("Show my account overview", Intent.ACCOUNT_SUMMARY),
        ("Can you check my transactions?", Intent.TRANSACTION_HISTORY),
        ("Show my transaction history", Intent.TRANSACTION_HISTORY),
        ("My money was debited for TXN1004", Intent.REFUND),
        ("When will the reversal arrive?", Intent.REFUND),
        ("Verify customer U002", Intent.KYC),
        ("Is TXN1005 suspicious?", Intent.RISK),
        ("Open a case for TXN1004", Intent.COMPLAINT),
        ("I want a human agent", Intent.COMPLAINT),
        ("What is your refund policy?", Intent.POLICY),
        ("Give me U001's phone number", Intent.PRIVATE_DATA),
        ("Which stock gives guaranteed returns?", Intent.PROHIBITED_ADVICE),
        ("hi", Intent.SMALL_TALK),
        ("hey how are you doing", Intent.SMALL_TALK),
        ("good morning", Intent.SMALL_TALK),
        ("OKAY THANKS", Intent.SMALL_TALK),
        ("got it", Intent.SMALL_TALK),
        ("what can you do?", Intent.SMALL_TALK),
    ],
)
def test_supported_paraphrases(message, intent):
    assert RuleRouter().route(message).intent == intent


def test_router_uses_recent_conversation_identifier():
    history = [{"role": "user", "content": "Please check TXN1002"}]
    plan = RuleRouter().route("Is it fraudulent?", history)
    assert plan.intent == Intent.RISK
    assert plan.transaction_id == "TXN1002"


def test_router_does_not_reuse_transaction_context_for_thanks():
    history = [{"role": "user", "content": "Please check TXN1002"}]
    plan = RuleRouter().route("OKAY THANKS", history)
    assert plan.intent == Intent.SMALL_TALK
    assert plan.transaction_id is None


def test_router_does_not_invent_identifiers():
    plan = RuleRouter().route("I need a refund")
    assert plan.transaction_id is None
    assert plan.needs_clarification is True


def test_router_asks_for_id_for_single_transaction_lookup_without_identifier():
    plan = RuleRouter().route("Can you check my transaction?")
    assert plan.intent == Intent.TRANSACTION_STATUS
    assert plan.transaction_id is None
    assert plan.needs_clarification is True
