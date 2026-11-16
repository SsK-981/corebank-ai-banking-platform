"""Regression checks for the signed-in transaction support workflow."""

from dataclasses import replace

import pytest

from backend import help_workflow, main

FAILED = "FAILABCDEF1234567890"
POSTED = "TXN1234567890ABCDEFS"


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
    assert not offered["case_offer"]
    assert offered["ticket_id"] is None
    offered = portal_chat("The ATM declined my withdrawal", **context)
    assert offered["case_offer"]
    assert offered["case_summary"] == "The ATM declined my withdrawal"
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
    assert portal_chat("Open a support case about my declined ATM withdrawal", **context)[
        "case_offer"
    ]
    portal_chat("Get help", action="select_transaction", transaction_reference=POSTED, **context)
    stale = portal_chat("Confirm", action="confirm_case", transaction_reference=FAILED, **context)
    assert stale["ticket_id"] is None


def test_failed_list_and_statement_use_the_correct_route(portal_chat):
    reply = portal_chat("Can you check my failed transactions?")
    assert [option["reference"] for option in reply["transaction_options"]] == [FAILED]
    no_failures = portal_chat("Can you check my failed transactions?", email="neha@example.com")
    assert "no recent failed transactions" in no_failures["response"]
    statement = portal_chat("Can I download my bank statement?")
    assert statement["next_action"] == "download_statement"
    assert "Download statement CSV" in statement["response"]


def test_cancelled_offer_cannot_be_confirmed(portal_chat):
    proposed = portal_chat("Open a support case about my missing ATM withdrawal")
    assert proposed["case_offer"]
    context = {"conversation_id": proposed["conversation_id"]}
    cancelled = portal_chat("Never mind, cancel it", **context)
    assert "cancelled" in cancelled["response"]
    assert portal_chat("Confirm case", action="confirm_case", **context)["ticket_id"] is None
