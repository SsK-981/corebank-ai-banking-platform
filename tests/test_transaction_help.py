"""Regression checks for the signed-in transaction support workflow."""

from dataclasses import replace

import pytest

from backend import help_workflow, main

FAILED = "FAILHELPCHECK001"
POSTED = "TXNHELPCHECK002"


@pytest.fixture
def portal_chat(client, monkeypatch):
    monkeypatch.setattr(main, "settings", replace(main.settings, banking_data_source="corebank"))
    transactions = {
        FAILED: {
            "found": True,
            "transaction_id": FAILED,
            "user_id": "U002",
            "amount": "100000.00",
            "status": "failed",
            "transaction_type": "withdraw",
            "failure_reason": "Insufficient balance",
            "source": "corebank",
        },
        POSTED: {
            "found": True,
            "transaction_id": POSTED,
            "user_id": "U002",
            "amount": "500.00",
            "status": "posted",
            "transaction_type": "transfer_sent",
            "source": "corebank",
        },
    }

    def lookup(reference, user):
        record = transactions.get(reference, {})
        return record if record.get("user_id") == user else {"found": False}

    def recent(user, *, limit):
        return {
            "found": True,
            "transactions": [
                record for record in transactions.values() if record["user_id"] == user
            ][:limit],
        }

    monkeypatch.setattr(help_workflow, "get_transaction_status", lookup)
    monkeypatch.setattr(help_workflow, "list_user_transactions", recent)

    def send(message, *, email="amit@example.com", **fields):
        response = client.post(
            "/internal/support/chat",
            headers={
                "X-Support-Service-Token": main.settings.support_service_token,
                "X-Authenticated-Customer-Email": email,
            },
            json={"message": message, **fields},
        )
        assert response.status_code == 200, response.text
        return response.json()

    return send


def test_explains_failed_transaction_without_copying_a_reference(portal_chat):
    suggestions = portal_chat("Why was my last withdrawal declined?")
    assert [item["reference"] for item in suggestions["transaction_options"]] == [FAILED]
    context = {"conversation_id": suggestions["conversation_id"]}
    chosen = portal_chat(
        "Get help",
        action="select_transaction",
        transaction_reference=FAILED,
        **context,
    )
    assert chosen["selected_transaction"]["reference"] == FAILED
    assert "Insufficient balance" in chosen["response"]
    portal_chat("Hello", **context)
    reason = portal_chat("Why did that one fail?", **context)
    assert "Insufficient balance" in reason["response"]
    refund = portal_chat("Will I get that money back?", **context)
    assert "not debited" in refund["response"].lower()


def test_everyday_transfer_problem_offers_owned_transaction_choices(portal_chat):
    response = portal_chat("I sent money to my friend but she still hasn't received it.")
    assert [item["reference"] for item in response["transaction_options"]] == [POSTED]
    assert response["ticket_id"] is None


def test_support_cases_require_confirmation_and_are_customer_scoped(portal_chat):
    assert portal_chat("Confirm", action="confirm_case")["ticket_id"] is None
    assert portal_chat("Escalate my complaint")["ticket_id"] is None
    owned = portal_chat(f"Check {FAILED}")
    context = {"conversation_id": owned["conversation_id"]}
    offered = portal_chat("Open a support case", **context)
    assert offered["case_offer"]
    assert offered["ticket_id"] is None
    first = portal_chat("Confirm", action="confirm_case", transaction_reference=FAILED, **context)
    assert first["ticket_id"]
    repeat = portal_chat("Confirm", action="confirm_case", transaction_reference=FAILED, **context)
    assert repeat["ticket_id"] == first["ticket_id"]
    listing = portal_chat("Any update on my ticket?", **context)
    matches = [case for case in listing["cases"] if case["ticket_id"] == first["ticket_id"]]
    assert len(matches) == 1
    assert matches[0]["transaction_reference"] == FAILED
    assert matches[0]["status"] == "open"
    assert portal_chat("My cases", email="neha@example.com", action="list_cases")["cases"] == []
    assert portal_chat(f"Check {FAILED}", email="neha@example.com")["selected_transaction"] is None


def test_changing_the_selected_transaction_invalidates_the_old_offer(portal_chat):
    context = {"conversation_id": portal_chat(f"Check {FAILED}")["conversation_id"]}
    assert portal_chat("Open a support case", **context)["case_offer"]
    portal_chat("Get help", action="select_transaction", transaction_reference=POSTED, **context)
    stale = portal_chat("Confirm", action="confirm_case", transaction_reference=FAILED, **context)
    assert stale["ticket_id"] is None
