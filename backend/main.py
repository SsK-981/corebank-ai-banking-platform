"""FastAPI application for the Fintech AI Agent Chatbot."""

import hmac
import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.agent_runtime import FintechAgent
from backend.config import get_settings
from backend.conversations import add_audit_log, add_message, get_or_create_conversation
from backend.database import get_db, init_db
from backend.help_workflow import answer_help
from backend.middleware import RequestContextMiddleware
from backend.models import AuditLog, ChatMessage, Ticket, Transaction, User
from backend.schemas import (
    AdminSummary,
    ChatRequest,
    ChatResponse,
    DevTokenRequest,
    KYCResponse,
    PrincipalResponse,
    RiskTransactionResponse,
    TicketCreate,
    TicketResponse,
    TokenResponse,
    TransactionResponse,
)
from backend.security import (
    CurrentPrincipal,
    Principal,
    authorize_user,
    issue_development_token,
    require_roles,
)
from backend.seed_data import seed_database
from backend.tools import (
    calculate_risk_score,
    create_support_ticket,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.seed_demo_data:
        seed_database()
    elif not settings.is_production:
        init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Authenticated transaction support, risk review, and escalation.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(RequestContextMiddleware)

agent = FintechAgent()


@app.get("/")
def health_check() -> dict:
    return {"status": "healthy", "service": "fintech-ai-agent", "version": "2.0.0"}


@app.get("/health/live")
def liveness() -> dict:
    return {"status": "alive"}


@app.get("/health/ready")
def readiness(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "available"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@app.post("/auth/dev-token", response_model=TokenResponse)
def development_token(payload: DevTokenRequest, db: Session = Depends(get_db)) -> dict:
    user_id = payload.user_id.upper() if payload.user_id else None
    if payload.role == "customer":
        if not user_id:
            raise HTTPException(status_code=400, detail="Customer tokens require a user_id")
        if db.scalar(select(User).where(User.user_id == user_id)) is None:
            raise HTTPException(status_code=404, detail="User not found")
    token, expires_in = issue_development_token(user_id, payload.role)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in}


@app.get("/auth/me", response_model=PrincipalResponse)
def current_identity(principal: CurrentPrincipal) -> dict:
    return {
        "subject": principal.subject,
        "user_id": principal.user_id,
        "roles": sorted(principal.roles),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    return _chat_impl(payload, principal, db, integrated=False)


def _chat_impl(
    payload: ChatRequest, principal: Principal, db: Session, *, integrated: bool
) -> dict:
    conversation = get_or_create_conversation(db, principal.subject, payload.conversation_id)
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(8)
        ).all()
    )
    history = [{"role": item.role, "content": item.content} for item in reversed(rows)]
    persisted_help_context = {}
    latest_assistant = next((row for row in rows if row.role == "assistant"), None)
    if latest_assistant:
        try:
            persisted_help_context = json.loads(latest_assistant.metadata_json or "{}").get(
                "help_context", {}
            )
        except (TypeError, ValueError):
            persisted_help_context = {}
    try:
        result = None
        if integrated and principal.user_id:
            result = answer_help(
                payload, principal, db, conversation.conversation_id, persisted_help_context
            )
        if result is None:
            result = agent.process_message(
                payload.message, principal, history, allow_ticket_creation=not integrated
            )
        # The conversation must exist before inserting its messages on PostgreSQL.
        db.flush()
        add_message(db, conversation.conversation_id, "user", payload.message)
        add_message(
            db,
            conversation.conversation_id,
            "assistant",
            result["response"],
            {
                "tools_used": result["tools_used"],
                "ticket_id": result.get("ticket_id"),
                "sources": result.get("sources", []),
                "help_context": persisted_help_context,
            },
        )
        add_audit_log(
            db,
            actor_subject=principal.subject,
            action="chat.processed",
            resource_type="conversation",
            resource_id=conversation.conversation_id,
            details={
                "tools_used": result["tools_used"],
                "escalated": result.get("escalated", False),
            },
        )
        db.commit()
        return {**result, "conversation_id": conversation.conversation_id}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The support agent could not process this request.",
        ) from exc


@app.post("/internal/support/chat", response_model=ChatResponse, include_in_schema=False)
def internal_support_chat(
    payload: ChatRequest,
    service_token: str | None = Header(default=None, alias="X-Support-Service-Token"),
    customer_email: str | None = Header(default=None, alias="X-Authenticated-Customer-Email"),
    db: Session = Depends(get_db),
) -> dict:
    """Same-origin CoreBank bridge; identity is supplied only by trusted Spring service."""
    if not service_token or not hmac.compare_digest(
        service_token.encode("utf-8"), settings.support_service_token.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid support service credentials")
    if settings.is_production or settings.banking_data_source != "corebank":
        raise HTTPException(status_code=503, detail="CoreBank support is unavailable")
    if not customer_email:
        raise HTTPException(status_code=400, detail="Authenticated customer email is required")
    normalized_email = customer_email.strip().casefold()
    user_id = next(
        (
            key
            for key, email in settings.corebank_customer_emails.items()
            if email.casefold() == normalized_email
        ),
        None,
    )
    if user_id is None:
        raise HTTPException(
            status_code=403,
            detail="Support chat is available only for the configured CoreBank demo customers.",
        )
    principal = Principal(
        subject=f"corebank-customer:{normalized_email}",
        user_id=user_id,
        roles=frozenset({"customer"}),
    )
    return _chat_impl(payload, principal, db, integrated=True)


@app.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def transaction_details(
    transaction_id: str,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> Transaction:
    transaction = db.scalar(
        select(Transaction).where(Transaction.transaction_id == transaction_id.upper())
    )
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    authorize_user(principal, transaction.user_id)
    add_audit_log(
        db,
        actor_subject=principal.subject,
        action="transaction.viewed",
        resource_type="transaction",
        resource_id=transaction.transaction_id,
    )
    db.commit()
    return transaction


@app.get("/users/{user_id}/kyc", response_model=KYCResponse)
def user_kyc(
    user_id: str,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> dict:
    normalized = user_id.upper()
    authorize_user(principal, normalized)
    user = db.scalar(select(User).where(User.user_id == normalized))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    add_audit_log(
        db,
        actor_subject=principal.subject,
        action="kyc.viewed",
        resource_type="user",
        resource_id=normalized,
    )
    db.commit()
    return {
        "user_id": user.user_id,
        "kyc_status": user.kyc_status,
        "account_status": user.account_status,
    }


@app.post("/tickets", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    principal: CurrentPrincipal,
    db: Session = Depends(get_db),
) -> Ticket:
    authorize_user(principal, payload.user_id)
    result = create_support_ticket(
        payload.user_id, payload.issue_type, payload.description, payload.priority
    )
    if not result.get("created"):
        error = result.get("error", "Ticket could not be created")
        code = 404 if "not found" in error.lower() else 400
        raise HTTPException(status_code=code, detail=error)
    ticket = db.scalar(select(Ticket).where(Ticket.ticket_id == result["ticket_id"]))
    if ticket is None:
        raise HTTPException(status_code=500, detail="Ticket could not be loaded")
    add_audit_log(
        db,
        actor_subject=principal.subject,
        action="ticket.created",
        resource_type="ticket",
        resource_id=ticket.ticket_id,
    )
    db.commit()
    return ticket


operator_access = require_roles("support", "admin")
admin_access = require_roles("admin")


@app.get("/admin/tickets", response_model=list[TicketResponse])
def list_tickets(
    principal: Principal = Depends(operator_access),
    db: Session = Depends(get_db),
) -> list[Ticket]:
    return list(db.scalars(select(Ticket).order_by(Ticket.created_at.desc())).all())


@app.get("/admin/high-risk-transactions", response_model=list[RiskTransactionResponse])
def high_risk_transactions(
    principal: Principal = Depends(operator_access),
    db: Session = Depends(get_db),
) -> list[dict]:
    transactions = db.scalars(
        select(Transaction)
        .where(Transaction.risk_level == "high")
        .order_by(Transaction.created_at.desc())
    ).all()
    response: list[dict] = []
    for transaction in transactions:
        risk = calculate_risk_score(transaction.transaction_id)
        response.append(
            {
                "transaction_id": transaction.transaction_id,
                "user_id": transaction.user_id,
                "amount": transaction.amount,
                "transaction_type": transaction.transaction_type,
                "status": transaction.status,
                "failed_attempts": transaction.failed_attempts,
                "risk_level": risk.get("risk_level", transaction.risk_level),
                "risk_reasons": risk.get("reasons", []),
                "created_at": transaction.created_at,
            }
        )
    return response


@app.get("/admin/summary", response_model=AdminSummary)
def admin_summary(
    principal: Principal = Depends(operator_access),
    db: Session = Depends(get_db),
) -> dict:
    def count(model, *conditions) -> int:
        statement = select(func.count()).select_from(model)
        if conditions:
            statement = statement.where(*conditions)
        return db.scalar(statement) or 0

    return {
        "total_users": count(User),
        "total_transactions": count(Transaction),
        "failed_transactions": count(Transaction, Transaction.status == "failed"),
        "pending_transactions": count(Transaction, Transaction.status == "pending"),
        "open_tickets": count(Ticket, Ticket.status == "open"),
        "high_risk_transactions": count(Transaction, Transaction.risk_level == "high"),
    }


@app.get("/admin/audit")
def audit_events(
    principal: Principal = Depends(admin_access),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)).all()
    return [
        {
            "id": row.id,
            "actor_subject": row.actor_subject,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]
