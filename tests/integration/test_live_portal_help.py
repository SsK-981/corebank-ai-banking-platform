"""Verify the customer Help workflow through the running, seeded portal."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_PORTAL_HELP_TESTS") != "1",
    reason="requires the running, seeded CoreBank and support services",
)

PORTAL_URL = os.getenv("COREBANK_PORTAL_URL", "http://127.0.0.1:8080")
AMIT_AUTH = ("amit@example.com", "password123")
NEHA_AUTH = ("neha@example.com", "password123")


def chat(message, *, auth=AMIT_AUTH, **context):
    response = requests.post(
        f"{PORTAL_URL}/customer/support/chat",
        auth=auth,
        json={"message": message, **context},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def failed_withdrawal_reference():
    accounts = requests.get(f"{PORTAL_URL}/customer/accounts", auth=AMIT_AUTH, timeout=10)
    accounts.raise_for_status()
    account_id = accounts.json()["content"][0]["accountId"]
    history = requests.get(
        f"{PORTAL_URL}/customer/accounts/{account_id}/transactions",
        auth=AMIT_AUTH,
        params={"size": 50},
        timeout=10,
    )
    history.raise_for_status()
    return next(
        item["referenceNumber"]
        for item in history.json()["content"]
        if item["type"] == "WITHDRAW" and item["status"] == "FAILED"
    )


def test_help_uses_signed_in_customer():
    response = requests.post(
        f"{PORTAL_URL}/customer/support/chat",
        json={"message": "What is my KYC status?"},
        timeout=10,
    )
    assert response.status_code in {401, 403}

    reply = chat("What is my KYC status?")
    assert "check_kyc_status" in reply["tools_used"], reply
    assert "pending" in reply["response"].lower(), reply
    assert reply["conversation_id"]


def test_transaction_help_keeps_context_and_confirms_one_case():
    reference = failed_withdrawal_reference()
    before = chat("My cases", action="list_cases")
    prior_case_ids = {case["ticket_id"] for case in before["cases"]}
    unsolicited_confirm = chat("Confirm opening a support case", action="confirm_case")
    assert unsolicited_confirm["ticket_id"] is None
    unsolicited_open = chat("Escalate my complaint")
    assert unsolicited_open["ticket_id"] is None

    suggestions = chat("Why was my last withdrawal declined?")
    assert any(item["reference"] == reference for item in suggestions["transaction_options"])
    selected = chat(
        "Get help with this transaction",
        action="select_transaction",
        transaction_reference=reference,
        conversation_id=suggestions["conversation_id"],
    )
    assert selected["selected_transaction"]["reference"] == reference
    assert selected["selected_transaction"]["status"].lower() == "failed"
    context = {"conversation_id": selected["conversation_id"]}

    chat("What is my account balance?", **context)
    explanation = chat("Why did that one fail?", **context)
    assert "insufficient balance" in explanation["response"].lower(), explanation
    refund = chat("Will I get that money back?", **context)
    assert "not debited" in refund["response"].lower(), refund
    offer = chat("Open a support case", **context)
    assert offer["case_offer"] is False
    assert offer["ticket_id"] is None
    offer = chat("The ATM declined my withdrawal", **context)
    assert offer["case_offer"] is True
    assert offer["case_summary"] == "The ATM declined my withdrawal"
    after_offer = chat("My cases", action="list_cases")
    assert {case["ticket_id"] for case in after_offer["cases"]} == prior_case_ids

    def confirm():
        return chat("Confirm opening a support case", action="confirm_case", **context)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, retry = [future.result() for future in [pool.submit(confirm), pool.submit(confirm)]]
    assert first["ticket_id"]
    assert retry["ticket_id"] == first["ticket_id"]

    status = chat("Any update on my ticket?", **context)
    matching = [case for case in status["cases"] if case["ticket_id"] == first["ticket_id"]]
    assert len(matching) == 1
    assert matching[0]["transaction_reference"] == reference
    assert matching[0]["status"] == "open"
    listed = chat("My cases", action="list_cases")
    assert {case["ticket_id"] for case in listed["cases"]} == prior_case_ids | {first["ticket_id"]}

    neha_cases = chat("My cases", auth=NEHA_AUTH, action="list_cases")
    assert not any(case["ticket_id"] == first["ticket_id"] for case in neha_cases["cases"])
    unowned = chat(
        "Get help with this transaction",
        auth=NEHA_AUTH,
        action="select_transaction",
        transaction_reference=reference,
    )
    assert unowned["selected_transaction"] is None


def test_separate_conversations_share_one_case_for_a_failed_transaction():
    # Create a distinct synthetic failure so this test can run after earlier cases.
    account = requests.get(f"{PORTAL_URL}/customer/accounts", auth=AMIT_AUTH, timeout=10).json()[
        "content"
    ][0]
    rejected = requests.post(
        f"{PORTAL_URL}/customer/accounts/{account['accountId']}/withdraw",
        auth=AMIT_AUTH,
        json={"amount": "9999999.00"},
        timeout=10,
    )
    assert rejected.status_code == 400
    reference = failed_withdrawal_reference()
    drafts = []
    for _ in range(6):
        selected = chat("Get help", action="select_transaction", transaction_reference=reference)
        context = {"conversation_id": selected["conversation_id"]}
        offered = chat("Open a support case because my withdrawal failed this morning", **context)
        assert offered["case_offer"]
        drafts.append(context)

    def confirm(context):
        return chat("Confirm", action="confirm_case", **context)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(confirm, drafts))
    case_ids = {reply["ticket_id"] for reply in results}
    assert len(case_ids) == 1 and None not in case_ids
    ticket_id = case_ids.pop()

    for _ in range(3):
        selected = chat("Get help", action="select_transaction", transaction_reference=reference)
        reply = chat("Raise another ticket for this", conversation_id=selected["conversation_id"])
        assert reply["ticket_id"] == ticket_id
        assert "already has a support case" in reply["response"]
        assert not reply["case_offer"]

    cases = chat("what are my active case")["cases"]
    assert sum(case["transaction_reference"] == reference for case in cases) == 1
    print(f"Six parallel confirmations and three later requests reused {ticket_id}")
