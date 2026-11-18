"""Deterministic intent routing used directly and as the model fallback."""

from __future__ import annotations

import re

from backend.agent_runtime.plan import AgentPlan, Intent

TRANSACTION_PATTERN = re.compile(r"\bTXN[A-Z0-9]+\b", re.IGNORECASE)
USER_PATTERN = re.compile(r"\bU\d+\b", re.IGNORECASE)
WORD_PATTERN = re.compile(r"[a-z0-9]+")
WALLET_BALANCE_PATTERN = re.compile(
    r"\bmy wallet balance\b|"
    r"\bmy wallet\b.*\b(?:how much|what amount|what balance)\b.*\b(?:spend|left|available)\b|"
    r"\b(?:how much|what amount)\b.*\b(?:left|available|spend)\b.*\bmy wallet\b"
)


class RuleRouter:
    """Recognize supported tasks without relying on an external service."""

    @staticmethod
    def _recent_identifier(pattern: re.Pattern, message: str, history: list[dict]) -> str | None:
        match = pattern.search(message)
        if match:
            return match.group(0).upper()
        for item in reversed(history[-8:]):
            if item.get("role") != "user":
                continue
            match = pattern.search(str(item.get("content", "")))
            if match:
                return match.group(0).upper()
        return None

    def route(self, message: str, history: list[dict] | None = None) -> AgentPlan:
        history = history or []
        lowered = message.lower()
        words = set(WORD_PATTERN.findall(lowered))
        transaction_id = self._recent_identifier(TRANSACTION_PATTERN, message, history)
        user_id = self._recent_identifier(USER_PATTERN, message, history)

        private_terms = (
            "mobile number",
            "phone number",
            "email address",
            "private details",
            "show email",
            "show phone",
            "reveal customer",
        )
        advice_terms = (
            "investment advice",
            "legal advice",
            "which stock",
            "buy shares",
            "guaranteed return",
            "trading tip",
        )
        if any(term in lowered for term in private_terms):
            return AgentPlan(intent=Intent.PRIVATE_DATA, confidence=1)
        if any(term in lowered for term in advice_terms):
            return AgentPlan(intent=Intent.PROHIBITED_ADVICE, confidence=1)

        small_talk_words = {
            "alright",
            "awesome",
            "hello",
            "hey",
            "hi",
            "hii",
            "hiii",
            "cool",
            "fine",
            "got",
            "gotcha",
            "great",
            "it",
            "namaste",
            "nice",
            "ok",
            "okay",
            "sure",
            "thanks",
            "thank",
            "you",
            "bye",
            "goodbye",
            "help",
        }
        capability_phrases = (
            "what can you do",
            "what all can you do",
            "how can you help",
            "what do you do",
            "who are you",
        )
        social_phrases = (
            "how are you",
            "how are u",
            "how are you doing",
            "how is it going",
            "how's it going",
            "are you there",
            "good morning",
            "good afternoon",
            "good evening",
            "nice to meet you",
        )

        complaint_words = (
            "complaint",
            "ticket",
            "raise",
            "escalate",
            "human agent",
            "support agent",
            "open a case",
            "report this",
            "dispute",
        )
        refund_words = (
            "refund",
            "reversal",
            "reversed",
            "deducted",
            "debited",
            "money back",
            "charged",
            "disappeared",
            "get it back",
            "wallet debit",
        )
        kyc_words = (
            "kyc",
            "verification",
            "verify customer",
            "identity check",
            "identity verified",
        )
        risk_words = ("risk", "fraud", "fraudulent", "suspicious", "safe transaction")
        account_summary_phrases = (
            "account balance",
            "how much money do i have",
            "how much is in my account",
            "how much is left",
            "how much do i have left",
            "how much have i got",
            "how much money have i got",
            "how much money is left",
            "my balance",
            "available balance",
            "account summary",
            "account overview",
            "show my account details",
            "customer profile",
            "my profile",
        )
        transaction_history_phrases = (
            "my transactions",
            "all transactions",
            "recent transactions",
            "transaction history",
            "payment history",
            "my payments",
            "all payments",
            "recent payments",
            "recent activity",
            "latest payments",
            "what did i pay",
            "what have i paid",
        )
        transaction_lookup_words = {
            "check",
            "show",
            "list",
            "view",
            "see",
            "find",
            "lookup",
            "status",
            "where",
        }
        policy_words = (
            "policy",
            "how long",
            "how many days",
            "what happens",
            "procedure",
            "timeline",
            "terms",
        )

        if any(term in lowered for term in complaint_words):
            return AgentPlan(
                intent=Intent.COMPLAINT,
                transaction_id=transaction_id,
                user_id=user_id,
                needs_clarification=not bool(user_id or transaction_id),
                escalate=True,
                confidence=0.94,
            )
        if any(term in lowered for term in policy_words) and not transaction_id:
            return AgentPlan(intent=Intent.POLICY, confidence=0.9)
        if any(term in lowered for term in refund_words):
            return AgentPlan(
                intent=Intent.REFUND,
                transaction_id=transaction_id,
                user_id=user_id,
                needs_clarification=not bool(transaction_id),
                confidence=0.93,
            )
        if any(term in lowered for term in kyc_words):
            return AgentPlan(
                intent=Intent.KYC,
                user_id=user_id,
                needs_clarification=not bool(user_id),
                confidence=0.95,
            )
        if any(term in lowered for term in risk_words):
            return AgentPlan(
                intent=Intent.RISK,
                transaction_id=transaction_id,
                needs_clarification=not bool(transaction_id),
                confidence=0.95,
            )
        if not TRANSACTION_PATTERN.search(message) and WALLET_BALANCE_PATTERN.search(lowered):
            return AgentPlan(intent=Intent.ACCOUNT_SUMMARY, user_id=user_id, confidence=1)
        if not TRANSACTION_PATTERN.search(message) and any(
            phrase in lowered for phrase in account_summary_phrases
        ):
            return AgentPlan(intent=Intent.ACCOUNT_SUMMARY, user_id=user_id, confidence=0.9)
        if not TRANSACTION_PATTERN.search(message) and any(
            phrase in lowered for phrase in transaction_history_phrases
        ):
            return AgentPlan(intent=Intent.TRANSACTION_HISTORY, user_id=user_id, confidence=0.92)
        if any(term in lowered for term in policy_words):
            return AgentPlan(intent=Intent.POLICY, confidence=0.86)
        if words and words <= small_talk_words:
            return AgentPlan(intent=Intent.SMALL_TALK, confidence=0.98)
        if any(phrase in lowered for phrase in capability_phrases):
            return AgentPlan(intent=Intent.SMALL_TALK, confidence=0.96)
        if any(phrase in lowered for phrase in social_phrases):
            return AgentPlan(intent=Intent.SMALL_TALK, confidence=0.96)
        if transaction_id:
            return AgentPlan(
                intent=Intent.TRANSACTION_STATUS,
                transaction_id=transaction_id,
                confidence=0.9,
            )
        if words & {"transaction", "payment", "txn"} and words & transaction_lookup_words:
            return AgentPlan(
                intent=Intent.TRANSACTION_STATUS,
                needs_clarification=True,
                confidence=0.82,
            )
        return AgentPlan(intent=Intent.GENERAL_SUPPORT, confidence=0.45)
