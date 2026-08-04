"""Pydantic request and response schemas for the API."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, min_length=36, max_length=36)


class ChatResponse(BaseModel):
    response: str
    tools_used: list[str] = Field(default_factory=list)
    ticket_id: str | None = None
    conversation_id: str
    escalated: bool = False
    sources: list[str] = Field(default_factory=list)


class TicketCreate(BaseModel):
    user_id: str = Field(min_length=2, max_length=20)
    issue_type: str = Field(min_length=2, max_length=50)
    description: str = Field(min_length=3, max_length=2000)
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticket_id: str
    user_id: str
    issue_type: str
    description: str
    priority: str
    status: str
    created_at: datetime


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: str
    user_id: str
    amount: Decimal
    transaction_type: str
    status: str
    failed_attempts: int
    risk_level: str
    created_at: datetime


class KYCResponse(BaseModel):
    user_id: str
    kyc_status: str
    account_status: str


class RiskTransactionResponse(TransactionResponse):
    risk_reasons: list[str] = Field(default_factory=list)


class AdminSummary(BaseModel):
    total_users: int
    total_transactions: int
    failed_transactions: int
    pending_transactions: int
    open_tickets: int
    high_risk_transactions: int


class DevTokenRequest(BaseModel):
    user_id: str | None = Field(default=None, max_length=20)
    role: str = Field(default="customer", pattern="^(customer|support|admin)$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class PrincipalResponse(BaseModel):
    subject: str
    user_id: str | None
    roles: list[str]
