"""Transaction selection and case handling for signed-in portal Help."""

import hashlib
import re
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.conversations import add_audit_log
from backend.models import SupportCaseTransaction, Ticket
from backend.schemas import ChatRequest
from backend.security import Principal
from backend.tools import get_transaction_status, list_user_transactions, summarize_customer_issue

_TRANSACTION_REFERENCE = re.compile(r"\b(?:TXN|FAIL)[A-Z0-9]+\b", re.IGNORECASE)


def _transaction_card(transaction: dict) -> dict:
    return {
        "reference": str(transaction.get("transaction_id") or transaction.get("reference_number")),
        "amount": str(transaction.get("amount") or "0"),
        "status": str(transaction.get("status") or "unknown"),
        "type": str(transaction.get("transaction_type") or "transaction"),
        "failure_reason": transaction.get("failure_reason"),
        "timestamp": transaction.get("timestamp"),
    }


def _case_list(db: Session, user_id: str) -> list[dict]:
    rows = db.execute(
        select(Ticket, SupportCaseTransaction.transaction_reference)
        .outerjoin(SupportCaseTransaction, SupportCaseTransaction.ticket_id == Ticket.ticket_id)
        .where(Ticket.user_id == user_id)
        .order_by(Ticket.created_at.desc())
    ).all()
    return [
        {
            "ticket_id": ticket.ticket_id,
            "status": ticket.status,
            "issue_type": ticket.issue_type,
            "transaction_reference": reference,
        }
        for ticket, reference in rows
    ]


def answer_help(
    payload: ChatRequest, principal: Principal, db: Session, conversation_id: str, context: dict
) -> dict | None:
    """Handle the portal's transaction and case workflow before general routing."""
    user_id = principal.user_id
    assert user_id is not None
    lowered = payload.message.strip().casefold()
    action = payload.action
    if action == "confirm_case":
        return _confirm_case(payload, principal, db, conversation_id, context, user_id)
    if action == "list_cases" or any(
        phrase in lowered
        for phrase in (
            "any update on my ticket",
            "any update on my case",
            "ticket status",
            "ticket update",
            "my cases",
            "my tickets",
        )
    ):
        cases = _case_list(db, user_id)
        answer = (
            "Here are your support cases."
            if cases
            else "I couldn’t find any support cases for your account."
        )
        return _reply(
            answer,
            cases=cases,
            tools_used=["list_owned_cases"],
        )

    message_match = _TRANSACTION_REFERENCE.search(payload.message)
    message_ref = message_match.group(0) if message_match else None
    typed_ref = message_ref or (
        payload.transaction_reference if action == "select_transaction" else None
    )
    vague_withdrawal = any(
        term in lowered
        for term in ("last withdrawal declined", "withdrawal declined", "withdrawal failed")
    )
    vague_recipient = any(
        term in lowered
        for term in (
            "friend didn't receive",
            "friend did not receive",
            "didn't receive it",
            "hasn't received",
            "has not received",
            "never got",
            "not received",
        )
    )
    vague_transaction = any(
        term in lowered
        for term in (
            "explain a transaction",
            "explain this transaction",
            "help with a failed transaction",
            "failed transaction",
            "why did that one fail",
            "why did it fail",
        )
    )
    selected_context = context.get("selected_transaction")
    contextual_transaction_followup = bool(
        selected_context
        and any(
            term in lowered
            for term in (
                "why did that one fail",
                "why did it fail",
                "why was it declined",
                "money back",
                "refund",
                "debited",
                "deducted",
                "reversed",
            )
        )
    )
    if contextual_transaction_followup and selected_context and not typed_ref:
        typed_ref = selected_context.get("reference")
    if action == "select_transaction" or message_ref or contextual_transaction_followup:
        if not typed_ref:
            return _reply(
                "Choose a transaction from your Activity list so I can check it.",
            )
        transaction = get_transaction_status(typed_ref, user_id)
        if transaction.get("error"):
            return _reply(
                "I couldn’t reach CoreBank to check that transaction. Please try again.",
                tools_used=["get_transaction_status"],
            )
        if not transaction.get("found") or transaction.get("user_id") != user_id:
            if action == "select_transaction" or message_ref:
                context.clear()
            return _reply(
                "I couldn’t find that transaction in your account. "
                "Choose one from your Activity list.",
                tools_used=["get_transaction_status"],
            )
        card = _transaction_card(transaction)
        context.update(selected_transaction=card)
        offered = context.get("case_offer_transaction")
        if offered and offered["reference"] != card["reference"]:
            context.pop("case_offer", None)
            context.pop("case_offer_transaction", None)
        if context.get("case_ticket_ref") != card["reference"]:
            context.pop("case_ticket_id", None)
            context.pop("case_ticket_ref", None)
        answer = _explain_transaction(card, from_corebank=transaction.get("source") == "corebank")
        return _reply(
            answer,
            selected_transaction=card,
            tools_used=["get_transaction_status"],
        )

    if vague_withdrawal or vague_recipient or vague_transaction:
        result = list_user_transactions(user_id, limit=50)
        if result.get("error"):
            return _reply(
                "I couldn’t load your recent transactions right now. Please try again.",
                tools_used=["list_user_transactions"],
            )
        candidates = result.get("transactions", [])
        if vague_withdrawal:
            candidates = [
                t for t in candidates if "withdraw" in str(t.get("transaction_type", "")).casefold()
            ]
        elif vague_recipient:
            candidates = [
                t
                for t in candidates
                if any(
                    x in str(t.get("transaction_type", "")).casefold()
                    for x in ("transfer", "payment")
                )
            ]
        elif vague_transaction:
            candidates = [
                t for t in candidates if str(t.get("status", "")).casefold() == "failed"
            ] or candidates
        options = [_transaction_card(t) for t in candidates[:5]]
        answer = (
            "Which transaction do you mean? Choose one below."
            if options
            else "I couldn’t find a recent match. Choose a transaction from Activity "
            "or share its reference."
        )
        return _reply(
            answer,
            transaction_options=options,
            tools_used=["list_user_transactions"],
        )

    # Integrated case requests are always staged for an explicit confirmation.
    if any(
        term in lowered
        for term in (
            "open a case",
            "open a ticket",
            "raise a ticket",
            "raise a case",
            "create a ticket",
            "create a case",
            "support case",
            "talk to support",
            "escalate this",
            "file a complaint",
            "raise a complaint",
            "dispute this",
        )
    ):
        selected = context.get("selected_transaction")
        context["case_description"] = payload.message
        context["case_offer"] = True
        context["case_offer_transaction"] = selected
        answer = (
            "I can open a support case"
            + (f" for {selected['reference']}" if selected else "")
            + ". Confirm to create it."
        )
        return _reply(answer, case_offer=True)
    return None


def _confirm_case(
    payload: ChatRequest,
    principal: Principal,
    db: Session,
    conversation_id: str,
    context: dict,
    user_id: str,
) -> dict:
    offered = context.get("case_offer_transaction")
    offered_ref = offered.get("reference") if offered else None
    requested_ref = payload.transaction_reference or offered_ref
    if context.get("case_ticket_id") and context.get("case_ticket_ref") == requested_ref:
        ticket = db.scalar(
            select(Ticket).where(
                Ticket.ticket_id == context["case_ticket_id"], Ticket.user_id == user_id
            )
        )
        if ticket:
            return _reply(
                f"Case {ticket.ticket_id} is {ticket.status}.",
                ticket_id=ticket.ticket_id,
            )
    if not context.get("case_offer") or requested_ref != offered_ref:
        return _reply(
            "I don’t have a matching case ready to confirm. Tell me what happened first.",
        )

    issue_type = "failed_transaction" if offered else "general_support"
    desc = summarize_customer_issue(context.get("case_description") or payload.message)
    stable_key = offered_ref or conversation_id
    ticket_id = "TCK-" + hashlib.sha256(f"{user_id}:{stable_key}".encode()).hexdigest()[:24].upper()
    dialect = db.get_bind().dialect.name
    insert_fn = (
        pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    )
    values = {
        "ticket_id": ticket_id,
        "user_id": user_id,
        "issue_type": issue_type,
        "description": desc,
        "priority": "medium",
        "status": "open",
    }
    ticket_was_new = False
    if insert_fn:
        inserted_ticket_id = db.scalar(
            insert_fn(Ticket)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["ticket_id"])
            .returning(Ticket.ticket_id)
        )
        ticket_was_new = inserted_ticket_id is not None
    elif db.scalar(select(Ticket).where(Ticket.ticket_id == ticket_id)) is None:
        db.add(Ticket(**values))
        db.flush()
        ticket_was_new = True
    if offered_ref and insert_fn:
        db.execute(
            insert_fn(SupportCaseTransaction)
            .values(ticket_id=ticket_id, transaction_reference=offered_ref)
            .on_conflict_do_nothing(index_elements=["transaction_reference"])
        )
    elif (
        offered_ref
        and db.scalar(
            select(SupportCaseTransaction).where(
                SupportCaseTransaction.transaction_reference == offered_ref
            )
        )
        is None
    ):
        db.add(SupportCaseTransaction(ticket_id=ticket_id, transaction_reference=offered_ref))
    owned_ticket = db.scalar(
        select(Ticket).where(Ticket.ticket_id == ticket_id, Ticket.user_id == user_id)
    )
    if owned_ticket is None:
        raise RuntimeError("Unable to verify ownership of the saved support case")
    if ticket_was_new:
        add_audit_log(
            db,
            actor_subject=principal.subject,
            action="ticket.created",
            resource_type="ticket",
            resource_id=ticket_id,
        )
    context["case_ticket_id"] = ticket_id
    context["case_ticket_ref"] = offered_ref
    context["case_offer"] = False
    return _reply(
        f"Case {ticket_id} is {owned_ticket.status}."
        + (f" Linked transaction: {offered_ref}." if offered_ref else ""),
        ticket_id=ticket_id,
        tools_used=["create_support_ticket"],
    )


def _explain_transaction(card: dict, *, from_corebank: bool) -> str:
    amount = f"₹{Decimal(card['amount']):,.2f}"
    reference = card["reference"]
    status = card["status"]
    if status.casefold() != "failed":
        return f"{reference} is marked {status} for {amount}. What would you like me to check?"

    reason = card["failure_reason"]
    details = f" CoreBank recorded: {reason}." if reason else ""
    if from_corebank and "withdraw" in card["type"].casefold() and reason == "Insufficient balance":
        return (
            f"{reference} is a failed withdrawal for {amount}.{details} "
            "The withdrawal was not debited, so there is no refund to track."
        )
    return (
        f"{reference} is marked failed for {amount}.{details} "
        "This record does not show whether a debit or refund occurred."
    )


def _reply(
    answer: str,
    *,
    selected_transaction: dict | None = None,
    transaction_options: list[dict] | None = None,
    cases: list[dict] | None = None,
    case_offer: bool = False,
    ticket_id: str | None = None,
    tools_used: list[str] | None = None,
) -> dict:
    return {
        "response": answer,
        "tools_used": tools_used or [],
        "ticket_id": ticket_id,
        "escalated": bool(ticket_id),
        "sources": [],
        "selected_transaction": selected_transaction,
        "transaction_options": transaction_options or [],
        "case_offer": case_offer,
        "cases": cases or [],
    }
