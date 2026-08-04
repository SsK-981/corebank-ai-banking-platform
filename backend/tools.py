"""Trusted tools used by the fintech agent.

When ``BANKING_DATA_SOURCE=corebank``, account, transaction, and risk tools call
the Java Spring Boot banking app through ``CoreBankClient``. Local SQLite remains
available as a demo fallback so the chatbot still runs when CoreBank is offline.
"""

from __future__ import annotations

import re
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from backend.config import get_settings
from backend.corebank_client import CoreBankClient, CoreBankError
from backend.database import SessionLocal
from backend.models import FAQ, Ticket, Transaction, User
from backend.risk_engine import score_transaction


def _corebank_enabled() -> bool:
    return get_settings().banking_data_source == "corebank"


def _fallback_enabled() -> bool:
    return get_settings().corebank_fallback_to_local


def _corebank_error_payload(user_id: str | None, error: Exception) -> dict:
    return {
        "found": False,
        "user_id": user_id.upper() if user_id else None,
        "source": "corebank",
        "error": str(error),
    }


def _local_get_account_summary(user_id: str) -> dict:
    normalized_id = user_id.strip().upper()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.user_id == normalized_id))
    if user is None:
        return {"found": False, "user_id": normalized_id, "source": "local"}
    balance = Decimal(str(user.wallet_balance or 0))
    return {
        "found": True,
        "user_id": user.user_id,
        "profile": {
            "user_id": user.user_id,
            "full_name": user.name,
            "source": "local",
        },
        "accounts": [
            {
                "account_id": user.user_id,
                "account_number": f"DEMO-{user.user_id}",
                "holder_name": user.name,
                "balance": balance,
                "active": user.account_status == "active",
                "owner_email": None,
            }
        ],
        "total_balance": balance,
        "active_accounts": 1 if user.account_status == "active" else 0,
        "source": "local",
    }


def get_account_summary(user_id: str) -> dict:
    """Return account/profile summary from CoreBank or the local demo store."""
    if _corebank_enabled():
        try:
            return CoreBankClient().account_summary(user_id)
        except CoreBankError as exc:
            if not _fallback_enabled():
                return _corebank_error_payload(user_id, exc)
    return _local_get_account_summary(user_id)


def _local_get_transaction_status(transaction_id: str) -> dict:
    """Fetch a transaction without returning private customer contact data."""
    normalized_id = transaction_id.strip().upper()
    with SessionLocal() as db:
        transaction = db.scalar(
            select(Transaction).where(Transaction.transaction_id == normalized_id)
        )
        if transaction is None:
            return {"found": False, "transaction_id": normalized_id, "source": "local"}
        return {
            "found": True,
            "transaction_id": transaction.transaction_id,
            "status": transaction.status,
            "amount": transaction.amount,
            "transaction_type": transaction.transaction_type,
            "user_id": transaction.user_id,
            "failed_attempts": transaction.failed_attempts,
            "risk_level": transaction.risk_level,
            "source": "local",
        }


def get_transaction_status(transaction_id: str, user_id: str | None = None) -> dict:
    """Fetch a transaction from CoreBank or the local demo store.

    In CoreBank mode, ``user_id`` is required so the client can use that customer's
    Basic Auth credentials. CoreBank then enforces account ownership.
    """
    normalized_id = transaction_id.strip().upper()
    if _corebank_enabled() and user_id:
        try:
            return CoreBankClient().get_transaction(user_id, normalized_id)
        except CoreBankError as exc:
            if not _fallback_enabled():
                return {
                    "found": False,
                    "transaction_id": normalized_id,
                    "user_id": user_id.upper(),
                    "source": "corebank",
                    "error": str(exc),
                }
    return _local_get_transaction_status(normalized_id)


def _local_list_user_transactions(user_id: str, limit: int = 5) -> dict:
    """Return recent transactions for one authorized customer without contact data."""
    normalized_id = user_id.strip().upper()
    safe_limit = max(1, min(limit, 10))
    with SessionLocal() as db:
        transactions = list(
            db.scalars(
                select(Transaction)
                .where(Transaction.user_id == normalized_id)
                .order_by(Transaction.created_at.desc(), Transaction.id.desc())
                .limit(safe_limit)
            ).all()
        )
    return {
        "found": bool(transactions),
        "user_id": normalized_id,
        "transactions": [
            {
                "transaction_id": transaction.transaction_id,
                "status": transaction.status,
                "amount": transaction.amount,
                "transaction_type": transaction.transaction_type,
                "risk_level": transaction.risk_level,
                "source": "local",
            }
            for transaction in transactions
        ],
        "source": "local",
    }


def list_user_transactions(user_id: str, limit: int = 5) -> dict:
    """Return recent transactions from CoreBank or the local demo store."""
    if _corebank_enabled():
        try:
            return CoreBankClient().list_transactions(user_id, limit=limit)
        except CoreBankError as exc:
            if not _fallback_enabled():
                payload = _corebank_error_payload(user_id, exc)
                payload["transactions"] = []
                return payload
    return _local_list_user_transactions(user_id, limit)


def _local_check_kyc_status(user_id: str) -> dict:
    """Return only the KYC and account fields needed for support."""
    normalized_id = user_id.strip().upper()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.user_id == normalized_id))
        if user is None:
            return {"found": False, "user_id": normalized_id, "source": "local"}
        return {
            "found": True,
            "user_id": user.user_id,
            "customer_name": user.name,
            "kyc_status": user.kyc_status,
            "account_status": user.account_status,
            "source": "local",
        }


def check_kyc_status(user_id: str) -> dict:
    """Return KYC information.

    In CoreBank mode, KYC and account state both come from the banking system of record.
    The local demo record is used only when the chatbot explicitly runs in local mode.
    """
    normalized_id = user_id.strip().upper()
    if _corebank_enabled():
        try:
            summary = CoreBankClient().account_summary(normalized_id)
            account_status = "active" if summary.get("active_accounts", 0) else "no_active_account"
            return {
                "found": True,
                "user_id": normalized_id,
                "customer_name": summary.get("profile", {}).get("full_name"),
                "kyc_status": summary.get("profile", {}).get("kyc_status", "not_available"),
                "account_status": account_status,
                "source": "corebank",
            }
        except CoreBankError as exc:
            if not _fallback_enabled():
                payload = _corebank_error_payload(normalized_id, exc)
                payload["kyc_status"] = "unavailable"
                payload["account_status"] = "unavailable"
                return payload
    return _local_check_kyc_status(normalized_id)


def _local_calculate_risk_score(transaction_id: str) -> dict:
    """Calculate and persist an explainable risk classification."""
    normalized_id = transaction_id.strip().upper()
    with SessionLocal() as db:
        transaction = db.scalar(
            select(Transaction).where(Transaction.transaction_id == normalized_id)
        )
        if transaction is None:
            return {"found": False, "transaction_id": normalized_id, "source": "local"}
        user = db.scalar(select(User).where(User.user_id == transaction.user_id))
        if user is None:
            return {
                "found": False,
                "transaction_id": normalized_id,
                "error": "Associated customer record was not found",
                "source": "local",
            }
        result = score_transaction(transaction.amount, transaction.failed_attempts, user.kyc_status)
        transaction.risk_level = result["risk_level"]
        db.commit()
        return {
            "found": True,
            "transaction_id": transaction.transaction_id,
            "user_id": transaction.user_id,
            "risk_level": result["risk_level"],
            "risk_score": result.get("score"),
            "reasons": result["reasons"],
            "manual_review_required": result["risk_level"] == "high",
            "source": "local",
        }


def calculate_risk_score(transaction_id: str, user_id: str | None = None) -> dict:
    """Return transaction/account risk from CoreBank or local demo rules."""
    normalized_id = transaction_id.strip().upper()
    if _corebank_enabled() and user_id:
        try:
            return CoreBankClient().risk_insights(user_id, transaction_id=normalized_id)
        except CoreBankError as exc:
            if not _fallback_enabled():
                return {
                    "found": False,
                    "transaction_id": normalized_id,
                    "user_id": user_id.upper(),
                    "source": "corebank",
                    "error": str(exc),
                }
    return _local_calculate_risk_score(normalized_id)


def calculate_account_risk(user_id: str) -> dict:
    """Return account-level risk from CoreBank or the highest local transaction risk."""
    normalized_id = user_id.strip().upper()
    if _corebank_enabled():
        try:
            return CoreBankClient().risk_insights(normalized_id)
        except CoreBankError as exc:
            if not _fallback_enabled():
                return _corebank_error_payload(normalized_id, exc)

    transactions = _local_list_user_transactions(normalized_id, limit=10)["transactions"]
    if not transactions:
        return {"found": False, "user_id": normalized_id, "source": "local"}

    risk_order = {"low": 0, "medium": 1, "high": 2}
    highest = max(transactions, key=lambda item: risk_order.get(item["risk_level"], -1))
    risk = _local_calculate_risk_score(highest["transaction_id"])
    risk["user_id"] = normalized_id
    return risk


def create_support_ticket(user_id: str, issue_type: str, description: str, priority: str) -> dict:
    """Validate the customer and create a concurrency-safe support ticket ID."""
    normalized_user_id = user_id.strip().upper()
    normalized_priority = priority.strip().lower()
    if normalized_priority not in {"low", "medium", "high"}:
        return {"created": False, "error": "Priority must be low, medium, or high"}
    if not description.strip():
        return {"created": False, "error": "Ticket description is required"}

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.user_id == normalized_user_id))
        if user is None:
            return {
                "created": False,
                "error": f"User {normalized_user_id} was not found",
            }
        ticket_id = f"TCK-{uuid4().hex[:12].upper()}"
        ticket = Ticket(
            ticket_id=ticket_id,
            user_id=normalized_user_id,
            issue_type=issue_type.strip().lower().replace(" ", "_"),
            description=description.strip(),
            priority=normalized_priority,
            status="open",
        )
        db.add(ticket)
        db.commit()
        return {"created": True, "ticket_id": ticket_id, "status": ticket.status}


def search_faq(query: str) -> dict:
    """Retrieve the best approved FAQ entry using transparent keyword scoring."""
    query_words = set(re.findall(r"[a-z0-9]+", query.lower()))
    stop_words = {
        "a",
        "an",
        "and",
        "for",
        "hello",
        "hey",
        "hi",
        "how",
        "i",
        "is",
        "my",
        "please",
        "the",
        "to",
        "what",
    }
    query_words -= stop_words
    with SessionLocal() as db:
        faqs = db.scalars(select(FAQ)).all()
    if not faqs:
        return {"found": False, "answer": "No approved policy records are available."}

    scored: list[tuple[int, FAQ]] = []
    for faq in faqs:
        searchable_words = set(
            re.findall(r"[a-z0-9]+", f"{faq.category} {faq.question} {faq.answer}".lower())
        )
        score = len(query_words & searchable_words)
        if faq.category.lower() in query_words:
            score += 3
        scored.append((score, faq))
    score, best_match = max(scored, key=lambda item: item[0])
    if score == 0:
        return {
            "found": False,
            "answer": "I could not find a matching approved policy.",
        }
    return {
        "found": True,
        "category": best_match.category,
        "question": best_match.question,
        "answer": best_match.answer,
        "source": f"faq:{best_match.category}:{best_match.id}",
        "score": score,
    }


def summarize_customer_issue(message: str) -> str:
    """Produce a short, ticket-safe summary without requiring an external model."""
    cleaned = re.sub(r"\s+", " ", message).strip()
    cleaned = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[redacted email]",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b\d{10,16}\b", "[redacted number]", cleaned)
    if len(cleaned) > 180:
        cleaned = f"{cleaned[:177].rstrip()}..."
    return cleaned
