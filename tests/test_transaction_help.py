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


def test_changing_the_selected_transaction_invalidates_the_old_offer(portal_chat, monkeypatch):
    reference = "FAIL0000000000000002"
    original_lookup = help_workflow.get_transaction_status

    def lookup(ref, user):
        if ref == reference:
            return {**original_lookup(FAILED, user), "transaction_id": reference}
        return original_lookup(ref, user)

    monkeypatch.setattr(help_workflow, "get_transaction_status", lookup)
    context = {"conversation_id": portal_chat(f"Check {reference}")["conversation_id"]}
    assert portal_chat("Open a support case about my declined ATM withdrawal", **context)[
        "case_offer"
    ]
    portal_chat("Get help", action="select_transaction", transaction_reference=POSTED, **context)
    stale = portal_chat(
        "Confirm", action="confirm_case", transaction_reference=reference, **context
    )
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


def test_short_failure_description_can_open_case_from_selected_transaction(
    portal_chat, monkeypatch
):
    reference = "FAIL0000000000000001"
    original_lookup = help_workflow.get_transaction_status

    def lookup(ref, user):
        if ref == reference:
            return {**original_lookup(FAILED, user), "transaction_id": reference}
        return original_lookup(ref, user)

    monkeypatch.setattr(help_workflow, "get_transaction_status", lookup)
    selected = portal_chat(f"Check {reference}")
    context = {"conversation_id": selected["conversation_id"]}
    prompt = portal_chat("Open a support case", **context)
    assert not prompt["case_offer"]
    followup = portal_chat("my transaction failed", **context)
    assert followup["case_offer"]
    assert followup["case_summary"] == "my transaction failed"
    assert followup["ticket_id"] is None
    confirmed = portal_chat("Confirm", action="confirm_case", **context)
    assert confirmed["ticket_id"]
    cases = portal_chat("My cases", action="list_cases", **context)["cases"]
    case = next(case for case in cases if case["ticket_id"] == confirmed["ticket_id"])
    assert case["summary"] == "my transaction failed"
    assert case["transaction_reference"] == reference


@pytest.mark.parametrize(
    "message",
    [
        "I think I was charged twice for the same payment.",
        "The ATM debited my account but did not dispense any cash.",
        "I am really worried because my money is missing. Please help me now.",
    ],
)
def test_natural_dispute_prepares_case_without_linking_unrelated_selection(portal_chat, message):
    selected = portal_chat(f"Check {FAILED}")
    context = {"conversation_id": selected["conversation_id"]}
    reply = portal_chat(message, **context)
    assert reply["case_offer"]
    assert reply["case_summary"] == message
    assert "refund" not in reply["response"].lower()
    assert reply["selected_transaction"] is None
    assert reply["ticket_id"] is None
    confirmed = portal_chat("Confirm", action="confirm_case", **context)
    assert confirmed["ticket_id"]
    cases = portal_chat("My cases", action="list_cases", **context)["cases"]
    assert cases[0]["summary"] == message
    assert cases[0]["transaction_reference"] is None


def test_conversational_complaint_opens_case_with_summary(portal_chat):
    reply = portal_chat(
        "I'd like to make a complaint about a payment that went to the wrong person."
    )
    assert reply["case_offer"]
    assert reply["case_summary"] == "a payment that went to the wrong person."
    assert reply["ticket_id"] is None


def test_viewed_case_is_used_for_followups_in_a_new_chat(portal_chat):
    draft = portal_chat("I want to file a complaint about a missing payment from yesterday.")
    confirmation = portal_chat(
        "Confirm", action="confirm_case", conversation_id=draft["conversation_id"]
    )
    case_id = confirmation["ticket_id"]
    assert case_id
    listing = portal_chat("tickets")
    context = {"conversation_id": listing["conversation_id"]}
    assert any(item["ticket_id"] == case_id for item in listing["cases"])
    selected = portal_chat(f"Show case {case_id}", **context)
    assert selected["cases"][0]["ticket_id"] == case_id
    for wording in (
        "whats the update on this",
        "Any news?",
        "Has it been resolved?",
        "Did anyone look at it?",
        "What is the case about?",
        "Where do we stand?",
    ):
        reply = portal_chat(wording, **context)
        assert [case["ticket_id"] for case in reply["cases"]] == [case_id], (wording, reply)
        assert "is open" in reply["response"]
        assert "missing payment" in reply["response"]
        assert reply["ticket_id"] is None


def test_privacy_question_does_not_fetch_account_data(portal_chat):
    reply = portal_chat("Can anyone at the bank see my account details?")
    assert "who at the bank" in reply["response"]
    assert reply["tools_used"] == []


def test_card_decline_explains_the_scope_and_offers_a_case(portal_chat):
    reply = portal_chat("My card payment keeps getting declined. Do you know why?")
    assert "Card authorization details aren’t available" in reply["response"]
    assert reply["case_offer"]
    assert reply["ticket_id"] is None


@pytest.mark.parametrize(
    "message",
    [
        "Maine kal paise bheje the, lekin saamne wale ko abhi tak nahi mile.",
        "My friend is still waiting for the money.",
    ],
)
def test_natural_nonreceipt_offers_a_recent_transfer(portal_chat, message):
    reply = portal_chat(message)
    assert [item["reference"] for item in reply["transaction_options"]] == [POSTED]


def test_transaction_status_followups_reuse_the_selected_record(portal_chat):
    selected = portal_chat(
        "Please help me with this transaction.",
        action="select_transaction",
        transaction_reference=FAILED,
    )
    context = {"conversation_id": selected["conversation_id"]}
    for wording in (
        "whats the update on this",
        "i have already selected the transaction",
        "Any news?",
    ):
        reply = portal_chat(wording, **context)
        assert reply["selected_transaction"]["reference"] == FAILED
        assert reply["tools_used"] == ["get_transaction_status"]
        assert "Insufficient balance" in reply["response"]
        assert not reply["cases"]

    portal_chat("Get help", action="select_transaction", transaction_reference=POSTED, **context)
    reply = portal_chat("What's the status now?", **context)
    assert reply["selected_transaction"]["reference"] == POSTED
    assert "posted" in reply["response"]


@pytest.mark.parametrize(
    "wording",
    [
        "whats the update on this",
        "Any progress?",
        "Can you tell me where this is up to?",
        "What's the status now?",
    ],
)
def test_same_status_question_across_help_states(portal_chat, wording):
    fresh = portal_chat(wording)
    assert "transaction or support case" in fresh["response"]
    assert not fresh["tools_used"]

    selected = portal_chat("Get help", action="select_transaction", transaction_reference=FAILED)
    conversation = {"conversation_id": selected["conversation_id"]}
    failed = portal_chat(wording, **conversation)
    assert failed["selected_transaction"]["reference"] == FAILED
    assert "Insufficient balance" in failed["response"]

    draft = portal_chat("File a complaint about my missing payment from yesterday")
    case = portal_chat("Confirm", action="confirm_case", conversation_id=draft["conversation_id"])
    case_id = case["ticket_id"]
    assert case_id
    portal_chat(f"Show case {case_id}", **conversation)
    assert portal_chat(wording, **conversation)["cases"][0]["ticket_id"] == case_id

    kyc = portal_chat("What's the status of my KYC?", **conversation)
    assert "check_kyc_status" in kyc["tools_used"]
    assert not kyc["cases"]

    explicit_transaction = portal_chat("Any update on my withdrawal?", **conversation)
    assert explicit_transaction["selected_transaction"]["reference"] == FAILED
    assert not explicit_transaction["cases"]
    assert portal_chat(wording, **conversation)["selected_transaction"]["reference"] == FAILED

    portal_chat(
        "Get help", action="select_transaction", transaction_reference=POSTED, **conversation
    )
    posted = portal_chat(wording, **conversation)
    assert posted["selected_transaction"]["reference"] == POSTED
    assert "posted" in posted["response"]
    assert not posted["cases"]

    different_kind = portal_chat("Any update on my withdrawal?", **conversation)
    assert [item["reference"] for item in different_kind["transaction_options"]] == [FAILED]
    assert not different_kind["selected_transaction"]


def test_existing_transaction_case_is_reused_across_conversations(portal_chat):
    first = portal_chat("Check " + FAILED)
    context = {"conversation_id": first["conversation_id"]}
    reply = portal_chat("Raise a ticket for this", **context)
    if reply["case_offer"] or not reply["ticket_id"]:
        if not reply["case_offer"]:
            reply = portal_chat("my transaction failed", **context)
        reply = portal_chat("Confirm", action="confirm_case", **context)
    ticket_id = reply["ticket_id"]
    assert ticket_id

    for _ in range(3):
        chosen = portal_chat("Get help", action="select_transaction", transaction_reference=FAILED)
        followup = portal_chat(
            "Can you raise a ticket for this?", conversation_id=chosen["conversation_id"]
        )
        assert followup["ticket_id"] == ticket_id
        assert "already has a support case" in followup["response"]
        assert not followup["case_offer"]
        assert followup["cases"][0]["transaction_reference"] == FAILED
    cases = portal_chat("My cases", action="list_cases")["cases"]
    assert sum(case["transaction_reference"] == FAILED for case in cases) == 1


@pytest.mark.parametrize(
    "wording",
    [
        "what are my active case",
        "my active cases",
        "any open ticket",
        "show my unresolved complaints",
    ],
)
def test_active_case_requests_use_owned_case_records(portal_chat, wording):
    reply = portal_chat(wording)
    assert reply["tools_used"] == ["list_owned_cases"]
    assert "get_account_summary" not in reply["tools_used"]
    assert all(case["status"] in {"open", "in_progress"} for case in reply["cases"])
    assert "active support cases" in reply["response"]


def test_active_cases_exclude_closed_records(portal_chat):
    from backend.database import SessionLocal
    from backend.models import Ticket

    with SessionLocal() as db:
        records = [
            Ticket(
                ticket_id="TCK-FILTEROPEN",
                user_id="U002",
                issue_type="general_support",
                description="Synthetic status filter check",
                status="open",
            ),
            Ticket(
                ticket_id="TCK-FILTERCLOSED",
                user_id="U002",
                issue_type="general_support",
                description="Synthetic closed filter check",
                status="closed",
            ),
        ]
        db.add_all(records)
        db.commit()
    active = portal_chat("what are my active case")["cases"]
    assert any(case["ticket_id"] == "TCK-FILTEROPEN" for case in active)
    assert all(case["ticket_id"] != "TCK-FILTERCLOSED" for case in active)


def test_clearing_selected_transaction_removes_context_and_linked_draft(portal_chat):
    selection = portal_chat(f"Check {POSTED}")
    context = {"conversation_id": selection["conversation_id"]}
    assert selection["selected_transaction"]["reference"] == POSTED
    draft = portal_chat("Open a case about my transfer not arriving yesterday", **context)
    assert draft["case_offer"]

    cleared = portal_chat("Clear selected transaction", action="clear_transaction", **context)
    assert cleared["selected_transaction"] is None
    assert not cleared["case_offer"]
    assert portal_chat("Confirm", action="confirm_case", **context)["ticket_id"] is None

    followup = portal_chat("What's the update on this?", **context)
    assert "transaction or support case" in followup["response"]
    assert followup["selected_transaction"] is None
    assert not followup["tools_used"]
    general = portal_chat("Something else, please", **context)
    assert "get_transaction_status" not in general["tools_used"]

    reselected = portal_chat(
        "Get help", action="select_transaction", transaction_reference=POSTED, **context
    )
    assert reselected["selected_transaction"]["reference"] == POSTED
