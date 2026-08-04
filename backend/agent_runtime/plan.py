"""Strict schemas shared by local and external intent routers."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Intent(StrEnum):
    SMALL_TALK = "small_talk"
    ACCOUNT_SUMMARY = "account_summary"
    TRANSACTION_STATUS = "transaction_status"
    TRANSACTION_HISTORY = "transaction_history"
    REFUND = "refund"
    KYC = "kyc"
    RISK = "risk"
    COMPLAINT = "complaint"
    POLICY = "policy"
    PRIVATE_DATA = "private_data"
    PROHIBITED_ADVICE = "prohibited_advice"
    GENERAL_SUPPORT = "general_support"


class AgentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    transaction_id: str | None = Field(default=None, pattern=r"^TXN[A-Z0-9]+$")
    user_id: str | None = Field(default=None, pattern=r"^U\d+$")
    needs_clarification: bool = False
    escalate: bool = False
    confidence: float = Field(default=0.5, ge=0, le=1)
