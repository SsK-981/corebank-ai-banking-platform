"""Human phrasing evaluation for customer Help.

These scenarios use the seeded synthetic customer and transaction fixtures.
The phrase variants intentionally test conversational follow-ups rather than
only the canonical wording in the tool examples.
"""

from dataclasses import replace

import pytest

from backend import help_workflow, main
from backend.agent_runtime.plan import AgentPlan, Intent

FAILED = "FAILABCDEF1234567890"
POSTED = "TXN1234567890ABCDEFS"


@pytest.fixture
def human_portal_chat(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "settings",
        replace(
            main.settings,
            banking_data_source="corebank",
            corebank_customer_emails={"U002": "amit@example.com"},
        ),
    )
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

    def send(message, *, conversation_id=None, action=None, transaction_reference=None):
        response = client.post(
            "/internal/support/chat",
            headers={
                "X-Support-Service-Token": main.settings.support_service_token,
                "X-Authenticated-Customer-Email": "amit@example.com",
            },
            json={
                "message": message,
                "conversation_id": conversation_id,
                "action": action,
                "transaction_reference": transaction_reference,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    return send


@pytest.mark.parametrize(
    "message,expected_tool,expected_phrase",
    [
        ("How much money have I got left?", "get_account_summary", None),
        ("Has my identity check gone through?", "check_kyc_status", None),
        ("Does anything look suspicious with TXN1002?", "calculate_risk_score", None),
    ],
)
def test_human_wording_reaches_the_relevant_feature(
    client, u002_headers, message, expected_tool, expected_phrase
):
    response = client.post("/chat", headers=u002_headers, json={"message": message})
    assert response.status_code == 200, response.text
    result = response.json()
    assert expected_tool in result["tools_used"], result
    if expected_phrase:
        assert expected_phrase in result["response"], result


@pytest.mark.parametrize(
    "message,expected_options",
    [
        ("Can I get a copy of my statement?", None),
        ("Show the payments that didn't go through.", [FAILED]),
        ("What's happening with my transfer to a friend?", [POSTED]),
    ],
)
def test_human_wording_routes_integrated_help_features(
    human_portal_chat, message, expected_options
):
    response = human_portal_chat(message)
    if expected_options is None:
        assert response["next_action"] == "download_statement", response
        assert "Download statement CSV" in response["response"]
    else:
        assert [
            item["reference"] for item in response["transaction_options"]
        ] == expected_options, response


@pytest.mark.parametrize(
    "followup",
    [
        "What's the update on this case?",
        "whats the update on this case",
        "Any news on my ticket?",
        "Did anyone look at it yet?",
        "Can you tell me where this is up to?",
    ],
)
def test_human_case_followup_returns_the_case_just_created(human_portal_chat, followup):
    offered = human_portal_chat("Open a case because my transaction failed")
    assert offered["case_offer"]
    conversation_id = offered["conversation_id"]
    created = human_portal_chat(
        "Confirm",
        conversation_id=conversation_id,
        action="confirm_case",
    )
    assert created["ticket_id"]
    response = human_portal_chat(followup, conversation_id=conversation_id)
    assert created["ticket_id"] in response["response"], response
    assert response["cases"][0]["status"] == "open"
    assert response["tools_used"] == ["list_owned_cases"]


@pytest.mark.parametrize(
    "issue",
    [
        "I was charged twice.",
        "Looks like they charged me twice for one payment",
        "The merchant debited my account twice.",
        "The ATM took the money but gave me no cash.",
        "I don't recognise this payment.",
        "My money has gone missing and I'm worried.",
    ],
)
def test_natural_dispute_wording_prepares_a_case_for_customer_confirmation(
    human_portal_chat, issue
):
    response = human_portal_chat(issue)
    assert response["case_offer"], response
    assert response["case_summary"] == issue
    assert response["ticket_id"] is None


@pytest.mark.parametrize(
    "phrase,expected_phrase",
    [
        ("Hello, can you help me?", "What can I help you with today?"),
        ("I need to speak to someone about my account.", "support case"),
        ("Can you check whether TXN1234567890ABCDEFS went through?", "posted"),
        ("Why did my last withdrawal get rejected?", "transaction"),
    ],
)
def test_other_common_support_phrasings_get_a_useful_next_step(
    human_portal_chat, phrase, expected_phrase
):
    response = human_portal_chat(phrase)
    assert expected_phrase.casefold() in response["response"].casefold(), response


def test_posted_transfer_not_received_offers_a_transaction_choice(human_portal_chat):
    result = human_portal_chat("My transfer went through but my friend hasn't received it.")
    assert [item["reference"] for item in result["transaction_options"]] == [POSTED]
    assert not result["ticket_id"]


def test_indirect_wallet_balance_stays_on_the_verified_route(human_portal_chat, monkeypatch):
    def unexpected_provider_route(*_args):
        pytest.fail("A recognized wallet balance question should use the local route")

    monkeypatch.setattr(main.agent.provider, "route", unexpected_provider_route)
    reply = human_portal_chat(
        "If I checked my wallet right now, what amount would I have to spend?"
    )
    assert reply["tools_used"] == ["get_account_summary"]
    assert "total available balance" in reply["response"]
    assert reply["ticket_id"] is None


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        AgentPlan(intent=Intent.ACCOUNT_SUMMARY, confidence=0.6),
        AgentPlan(intent=Intent.ACCOUNT_SUMMARY, confidence=0.99, user_id="U003"),
        AgentPlan(intent=Intent.KYC, confidence=0.99, transaction_id="TXN1001"),
        AgentPlan(intent=Intent.COMPLAINT, confidence=0.99, escalate=True),
        AgentPlan(intent=Intent.REFUND, confidence=0.99),
    ],
)
def test_integrated_help_rejects_unavailable_or_untrusted_model_plans(
    human_portal_chat, monkeypatch, candidate
):
    monkeypatch.setattr(main.agent.provider, "route", lambda *_: candidate)
    reply = human_portal_chat("One quick question about something unusual")
    assert not reply["tools_used"]
    assert not reply["ticket_id"]
    assert not reply["case_offer"]


def test_model_can_select_read_intent_without_receiving_conversation_history(
    human_portal_chat, monkeypatch
):
    def route(message, history):
        assert message == "Has the bank finished checking who I am yet?"
        assert history == []
        return AgentPlan(intent=Intent.KYC, confidence=0.95)

    previous = human_portal_chat("What is my balance?")
    monkeypatch.setattr(main.agent.provider, "route", route)
    reply = human_portal_chat(
        "Has the bank finished checking who I am yet?",
        conversation_id=previous["conversation_id"],
    )
    assert reply["tools_used"] == ["check_kyc_status"]
    assert "pending" in reply["response"].lower()


def test_integrated_help_keeps_rules_and_templates_even_with_model_configured(
    human_portal_chat, monkeypatch
):
    def unexpected_model_call(*_args, **_kwargs):
        pytest.fail("Known Help requests stay on the deterministic path")

    monkeypatch.setattr(main.agent.provider, "route", unexpected_model_call)
    monkeypatch.setattr(main.agent.provider, "polish_response", unexpected_model_call)
    assert human_portal_chat("Hi")["response"] == "Hello! How can I help you today?"
    assert human_portal_chat("What is my balance?")["tools_used"] == ["get_account_summary"]
    assert human_portal_chat("They charged me twice for the same thing.")["case_offer"]


@pytest.mark.parametrize(
    "message,expected_action,expected_tools",
    [
        ("can you send neha 5000 from my account", "open_transfer", []),
        ("I want to transfer ₹500 to Neha", "open_transfer", []),
        ("Could you send money to Neha?", "open_transfer", []),
        ("Send my bank statement", "download_statement", []),
        ("Can you send me my statement for last month?", "download_statement", []),
        ("Show my recent transactions from my account", None, ["list_user_transactions"]),
        ("How much money is left in my account?", None, ["get_account_summary"]),
        ("Neha hasn't received the money I sent from my account", None, ["list_user_transactions"]),
        ("My statement shows I was charged twice for a payment", None, []),
    ],
)
def test_help_routes_by_request_when_account_words_overlap(
    human_portal_chat, message, expected_action, expected_tools
):
    reply = human_portal_chat(message)
    assert reply["next_action"] == expected_action
    assert reply["tools_used"] == expected_tools
    assert not reply["ticket_id"]
    if "charged twice" in message:
        assert reply["case_offer"]


@pytest.mark.parametrize(
    "message,action,tool,case_offer",
    [
        ("Could you move 2500 to Neha from my account?", "open_transfer", None, False),
        ("Neha didn't get the money I sent yesterday", None, "list_user_transactions", False),
        ("Please open a support case about my missing payment", None, None, True),
        ("Can I change the holder name on my account?", None, None, False),
    ],
)
def test_banking_intent_benchmark_regressions(
    human_portal_chat, monkeypatch, message, action, tool, case_offer
):
    def unexpected_model_call(*args, **kwargs):
        pytest.fail("The explicit request should be handled by CoreBank rules")

    monkeypatch.setattr(main.agent.provider, "route", unexpected_model_call)
    response = human_portal_chat(message)
    assert response["next_action"] == action
    assert response["tools_used"] == ([tool] if tool else [])
    assert response["case_offer"] is case_offer
    assert response["ticket_id"] is None
    if "holder name" in message:
        assert "Contact support" in response["response"]
