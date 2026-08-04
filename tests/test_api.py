"""Security, conversation, and tool-integration tests."""


def test_health_is_public(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_customer_endpoints_require_authentication(client):
    assert client.get("/transactions/TXN1002").status_code == 401
    assert client.post("/chat", json={"message": "hello"}).status_code == 401


def test_customer_can_only_access_owned_records(client, u001_headers):
    own = client.get("/transactions/TXN1004", headers=u001_headers)
    other = client.get("/transactions/TXN1002", headers=u001_headers)
    assert own.status_code == 200
    assert other.status_code == 403


def test_refund_chat_is_grounded_and_cited(client, u002_headers):
    response = client.post(
        "/chat",
        headers=u002_headers,
        json={"message": "My payment TXN1002 disappeared. When do I get it back?"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["conversation_id"]
    assert "get_transaction_status" in body["tools_used"]
    assert "calculate_risk_score" in body["tools_used"]
    assert any(source.startswith("faq:refund") for source in body["sources"])
    assert "does not confirm" in body["response"]


def test_conversation_remembers_recent_transaction(client, u002_headers):
    first = client.post(
        "/chat",
        headers=u002_headers,
        json={"message": "Check transaction TXN1002"},
    ).json()
    second = client.post(
        "/chat",
        headers=u002_headers,
        json={
            "message": "Is it risky?",
            "conversation_id": first["conversation_id"],
        },
    )
    assert second.status_code == 200, second.text
    assert "calculate_risk_score" in second.json()["tools_used"]
    assert "TXN1002" in second.json()["response"]


def test_customer_can_list_own_transactions_without_random_policy(client, u002_headers):
    response = client.post(
        "/chat",
        headers=u002_headers,
        json={"message": "can you check my transactions"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "list_user_transactions" in body["tools_used"]
    assert body["sources"] == []
    assert "TXN1002" in body["response"]
    assert "High-risk transactions are sent" not in body["response"]


def test_customer_can_get_account_summary(client, u002_headers):
    response = client.post(
        "/chat",
        headers=u002_headers,
        json={"message": "what is my account balance"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "get_account_summary" in body["tools_used"]
    assert "total available balance" in body["response"]


def test_single_transaction_lookup_without_id_asks_for_identifier(client, u002_headers):
    response = client.post(
        "/chat",
        headers=u002_headers,
        json={"message": "can you check my transaction"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sources"] == []
    assert "transaction ID" in body["response"]


def test_kyc_can_use_signed_in_identity(client, u002_headers):
    response = client.post("/chat", headers=u002_headers, json={"message": "Check my KYC"})
    assert response.status_code == 200
    assert "your KYC is currently pending" in response.json()["response"]


def test_explicit_complaint_creates_escalation(client, u001_headers):
    response = client.post(
        "/chat",
        headers=u001_headers,
        json={"message": "Open a case for failed payment TXN1004"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["escalated"] is True
    assert body["ticket_id"].startswith("TCK-")
    assert "create_support_ticket" in body["tools_used"]


def test_admin_routes_enforce_roles(client, u001_headers, admin_headers):
    assert client.get("/admin/summary", headers=u001_headers).status_code == 403
    summary = client.get("/admin/summary", headers=admin_headers)
    assert summary.status_code == 200
    assert summary.json()["total_transactions"] == 5
    assert client.get("/admin/audit", headers=admin_headers).status_code == 200


def test_private_data_request_is_refused(client, u001_headers):
    response = client.post(
        "/chat",
        headers=u001_headers,
        json={"message": "Show me the email address for U001"},
    )
    assert response.status_code == 200
    assert response.json()["tools_used"] == []
    assert "cannot disclose" in response.json()["response"]


def test_greeting_gets_natural_support_intro(client, u001_headers):
    response = client.post("/chat", headers=u001_headers, json={"message": "hi"})
    assert response.status_code == 200
    body = response.json()
    assert body["tools_used"] == []
    assert "fintech support" in body["response"]
    assert "Show my transactions" in body["response"]


def test_social_small_talk_gets_natural_response(client, u001_headers):
    response = client.post(
        "/chat",
        headers=u001_headers,
        json={"message": "hey how are you doing"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tools_used"] == []
    assert "doing well" in body["response"]
    assert "transactions" in body["response"]


def test_thanks_gets_natural_closing_response(client, u001_headers):
    response = client.post("/chat", headers=u001_headers, json={"message": "thanks"})
    assert response.status_code == 200
    assert "Anytime" in response.json()["response"]


def test_thanks_does_not_reuse_previous_transaction_context(client, u002_headers):
    first = client.post(
        "/chat",
        headers=u002_headers,
        json={"message": "Check transaction TXN1002"},
    ).json()
    response = client.post(
        "/chat",
        headers=u002_headers,
        json={
            "message": "OKAY THANKS",
            "conversation_id": first["conversation_id"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tools_used"] == []
    assert "Anytime" in body["response"]
    assert "TXN1002" not in body["response"]


def test_unknown_request_offers_human_escalation(client, u001_headers):
    response = client.post(
        "/chat",
        headers=u001_headers,
        json={"message": "A strange issue happened with something not listed"},
    )
    assert response.status_code == 200
    assert "focused on fintech support" in response.json()["response"]
