"""Safe orchestration of intent routing, authorization, tools, and responses."""

from __future__ import annotations

from typing import Any

from backend.agent_runtime.plan import AgentPlan, Intent
from backend.agent_runtime.provider import OpenAICompatibleProvider
from backend.agent_runtime.router import RuleRouter
from backend.security import Principal
from backend.tools import (
    calculate_account_risk,
    calculate_risk_score,
    check_kyc_status,
    create_support_ticket,
    get_account_summary,
    get_transaction_status,
    list_user_transactions,
    search_faq,
    summarize_customer_issue,
)


class FintechAgent:
    """Route requests to trusted local operations and produce grounded responses."""

    def __init__(self) -> None:
        self.rule_router = RuleRouter()
        self.provider = OpenAICompatibleProvider()

    def _plan(self, message: str, history: list[dict]) -> AgentPlan:
        local_plan = self.rule_router.route(message, history)
        if local_plan.confidence == 1 or local_plan.intent in {
            Intent.SMALL_TALK,
            Intent.PRIVATE_DATA,
            Intent.PROHIBITED_ADVICE,
        }:
            return local_plan
        provider_plan = self.provider.route(message, history)
        if provider_plan is None or provider_plan.confidence < 0.55:
            return local_plan
        updates: dict[str, str] = {}
        if not provider_plan.transaction_id and local_plan.transaction_id:
            updates["transaction_id"] = local_plan.transaction_id
        if not provider_plan.user_id and local_plan.user_id:
            updates["user_id"] = local_plan.user_id
        return provider_plan.model_copy(update=updates) if updates else provider_plan

    def _plan_customer_help(self, message: str, history: list[dict]) -> AgentPlan:
        local_plan = self.rule_router.route(message, history)
        if local_plan.intent != Intent.GENERAL_SUPPORT:
            return local_plan

        # The provider sees only the current, redacted message. References and
        # conversation context stay in the signed-in application.
        candidate = self.provider.route(message, [])
        if (
            candidate is None
            or candidate.confidence < 0.75
            or candidate.intent
            not in {Intent.ACCOUNT_SUMMARY, Intent.TRANSACTION_HISTORY, Intent.KYC}
            or candidate.user_id
            or candidate.transaction_id
            or candidate.escalate
        ):
            return local_plan
        return AgentPlan(intent=candidate.intent, confidence=candidate.confidence)

    @staticmethod
    def _authorized(principal: Principal, user_id: str) -> bool:
        return principal.can_access_all_customers or (
            principal.user_id is not None and principal.user_id.upper() == user_id.upper()
        )

    @staticmethod
    def _result(
        response: str,
        tools_used: list[str] | None = None,
        *,
        ticket_id: str | None = None,
        escalated: bool = False,
        sources: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "response": response,
            "tools_used": list(dict.fromkeys(tools_used or [])),
            "ticket_id": ticket_id,
            "escalated": escalated,
            "sources": sources or [],
        }

    def process_message(
        self,
        message: str,
        principal: Principal,
        history: list[dict] | None = None,
        *,
        allow_ticket_creation: bool = True,
    ) -> dict[str, Any]:
        history = history or []
        cleaned_message = message.strip()
        plan = (
            self._plan(cleaned_message, history)
            if allow_ticket_creation
            else self._plan_customer_help(cleaned_message, history)
        )
        if plan.intent == Intent.SMALL_TALK:
            response = self._small_talk_response(cleaned_message)
            if allow_ticket_creation:
                response = self._polish_response(
                    message=cleaned_message,
                    plan=plan,
                    response=response,
                    tools_used=[],
                    sources=[],
                )
            return self._result(response)
        if plan.intent == Intent.PRIVATE_DATA:
            return self._result(
                "I cannot disclose customer contact or private account details. "
                "I can help with records you are authorized to access."
            )
        if plan.intent == Intent.PROHIBITED_ADVICE:
            return self._result(
                "I can help with payments, wallets, KYC, risk reviews, and support "
                "tickets, but I cannot provide investment or legal advice."
            )

        if plan.intent == Intent.GENERAL_SUPPORT and not allow_ticket_creation:
            return self._result(
                "Could you share a little more about what happened? "
                "For a payment issue, tell me the amount or choose the transaction in Activity."
            )

        results: dict[str, Any] = {}
        tools_used: list[str] = []
        sources: list[str] = []
        transaction_id = plan.transaction_id
        user_id = plan.user_id

        if transaction_id:
            lookup_user_id = user_id or principal.user_id
            transaction = get_transaction_status(transaction_id, lookup_user_id)
            tools_used.append("get_transaction_status")
            if transaction.get("found"):
                if not self._authorized(principal, transaction["user_id"]):
                    return self._result(
                        "I cannot access that transaction for the signed-in customer.",
                        tools_used,
                    )
                user_id = transaction["user_id"]
            results["transaction"] = transaction

        if user_id and not self._authorized(principal, user_id):
            return self._result("I cannot access that customer record.", tools_used)

        if plan.intent == Intent.ACCOUNT_SUMMARY:
            user_id = user_id or principal.user_id
            if user_id:
                results["account_summary"] = get_account_summary(user_id)
                tools_used.append("get_account_summary")

        if plan.intent == Intent.TRANSACTION_HISTORY:
            user_id = user_id or principal.user_id
            if user_id:
                results["transactions"] = list_user_transactions(user_id)
                tools_used.append("list_user_transactions")

        if plan.intent == Intent.KYC:
            user_id = user_id or principal.user_id
            if user_id:
                results["kyc"] = check_kyc_status(user_id)
                tools_used.append("check_kyc_status")

        if (
            transaction_id
            and plan.intent
            in {
                Intent.RISK,
                Intent.REFUND,
                Intent.COMPLAINT,
            }
            and results.get("transaction", {}).get("found")
        ):
            results["risk"] = calculate_risk_score(transaction_id, user_id or principal.user_id)
            tools_used.append("calculate_risk_score")

        if plan.intent == Intent.RISK and not transaction_id:
            user_id = user_id or principal.user_id
            if user_id:
                results["risk"] = calculate_account_risk(user_id)
                tools_used.append("calculate_account_risk")

        if plan.intent in {Intent.REFUND, Intent.POLICY}:
            policy_query = f"refund {message}" if plan.intent == Intent.REFUND else message
            results["faq"] = search_faq(policy_query)
            tools_used.append("search_faq")
            if results["faq"].get("source"):
                sources.append(results["faq"]["source"])

        ticket_id: str | None = None
        if plan.intent == Intent.COMPLAINT and allow_ticket_creation:
            user_id = user_id or principal.user_id
            if user_id:
                risk_level = results.get("risk", {}).get("risk_level")
                priority = "high" if risk_level == "high" else "medium"
                results["ticket"] = create_support_ticket(
                    user_id=user_id,
                    issue_type=self._issue_type(message.lower()),
                    description=summarize_customer_issue(message),
                    priority=priority,
                )
                tools_used.extend(["summarize_customer_issue", "create_support_ticket"])
                ticket_id = results["ticket"].get("ticket_id")
        elif plan.intent == Intent.COMPLAINT:
            return self._result(
                "Choose a transaction from Activity or ask me to open a support case. "
                "I’ll ask you to confirm before creating it."
            )

        response = self._compose(plan, results, transaction_id, user_id)
        if allow_ticket_creation:
            response = self._polish_response(
                message=cleaned_message,
                plan=plan,
                response=response,
                tools_used=tools_used,
                sources=sources,
            )
        escalated = bool(ticket_id)
        return self._result(
            response,
            tools_used,
            ticket_id=ticket_id,
            escalated=escalated,
            sources=sources,
        )

    def _polish_response(
        self,
        *,
        message: str,
        plan: AgentPlan,
        response: str,
        tools_used: list[str],
        sources: list[str],
    ) -> str:
        # Financial/policy facts are already presented by deterministic templates.
        # The model may polish only tool-free conversation such as greetings.
        if tools_used or sources:
            return response
        polished = self.provider.polish_response(
            message=message,
            intent=plan.intent.value,
            grounded_response=response,
            tools_used=tools_used,
            sources=sources,
        )
        return polished or response

    @staticmethod
    def _small_talk_response(message: str) -> str:
        lowered = message.lower()
        if any(term in lowered for term in ("thank", "thanks", "okay", "ok", "got it", "gotcha")):
            return "Anytime. Let me know if you need anything else."
        if any(term in lowered for term in ("bye", "goodbye")):
            return "Goodbye! If another payment or account issue comes up, I’ll be here to help."
        if any(
            phrase in lowered
            for phrase in (
                "how are you",
                "how are u",
                "how are you doing",
                "how is it going",
                "how's it going",
            )
        ):
            return "I’m doing well, thank you. How can I help you today?"
        for greeting in ("Good morning", "Good afternoon", "Good evening"):
            if greeting.lower() in lowered:
                return f"{greeting}. How can I help you today?"
        if "are you there" in lowered:
            return "Yes, I’m here. How can I help?"
        if any(
            phrase in lowered
            for phrase in (
                "what can you do",
                "what all can you do",
                "how can you help",
                "what do you do",
                "who are you",
                "help",
            )
        ):
            return (
                "I can help you find a transaction, check your KYC status, "
                "or get support with an account issue."
            )
        return "Hello! How can I help you today?"

    @staticmethod
    def _format_money(amount: Any) -> str:
        return f"₹{amount:,.2f}"

    @staticmethod
    def _friendly_transaction_type(transaction_type: str) -> str:
        return transaction_type.replace("_", " ").lower()

    @staticmethod
    def _issue_type(lowered: str) -> str:
        if "kyc" in lowered or "verification" in lowered:
            return "kyc_issue"
        if any(word in lowered for word in ("wallet", "deducted", "debited")):
            return "wallet_issue"
        if "refund" in lowered:
            return "refund_issue"
        if any(word in lowered for word in ("failed", "transaction", "payment")):
            return "failed_transaction"
        return "general_support"

    @staticmethod
    def _compose(
        plan: AgentPlan,
        results: dict[str, Any],
        transaction_id: str | None,
        user_id: str | None,
    ) -> str:
        parts: list[str] = []
        transaction = results.get("transaction")
        if transaction:
            if not transaction.get("found"):
                parts.append(
                    f"I couldn’t find transaction {transaction['transaction_id']}. "
                    "Please double-check the ID and try again."
                )
            else:
                friendly_type = FintechAgent._friendly_transaction_type(
                    transaction["transaction_type"]
                )
                parts.append(
                    f"I found it — {transaction['transaction_id']} is marked "
                    f"{transaction['status']} for "
                    f"{FintechAgent._format_money(transaction['amount'])} "
                    f"as a {friendly_type}."
                )
                if transaction["status"] == "failed":
                    parts.append(
                        "That means the payment did not complete. A failed status does not "
                        "confirm that a refund is already complete, so a debit may still "
                        "need refund or reversal tracking."
                    )
                elif transaction["status"] == "pending":
                    parts.append(
                        "It’s still pending, so I would not treat it as completed or refunded yet."
                    )
                elif transaction["status"] == "success":
                    parts.append(
                        "Good news — it is recorded as successful in the available records."
                    )

        kyc = results.get("kyc")
        if kyc:
            if kyc.get("found"):
                parts.append(
                    f"For {kyc['user_id']}, your KYC is currently {kyc['kyc_status']} "
                    f"and the account is {kyc['account_status']}."
                )
                if kyc["kyc_status"] == "pending":
                    parts.append(
                        "If you already submitted documents, it may still be under review."
                    )
            else:
                parts.append(f"I couldn’t find user {kyc['user_id']} in the approved records.")

        account_summary = results.get("account_summary")
        if account_summary:
            if account_summary.get("found"):
                profile = account_summary.get("profile", {})
                accounts = account_summary.get("accounts", [])
                active_accounts = account_summary.get("active_accounts", 0)
                total_balance = FintechAgent._format_money(account_summary["total_balance"])
                name = profile.get("full_name") or account_summary["user_id"]
                account_bits = [
                    f"{account.get('account_number')} has "
                    f"{FintechAgent._format_money(account.get('balance', 0))}"
                    for account in accounts[:3]
                ]
                parts.append(
                    f"Here’s the account summary for {name}: {active_accounts} active "
                    f"account(s), total available balance {total_balance}."
                )
                if account_bits:
                    parts.append("Accounts I can access: " + "; ".join(account_bits) + ".")
            elif account_summary.get("error"):
                parts.append(
                    "I couldn’t reach the connected banking system for the account summary. "
                    "Please try again in a moment."
                )
            else:
                parts.append(
                    f"I couldn’t find an account summary for {account_summary['user_id']}."
                )

        transaction_history = results.get("transactions")
        if transaction_history:
            if transaction_history.get("found"):
                formatted_transactions = [
                    f"{item['transaction_id']} — {item['status']} "
                    f"{FintechAgent._friendly_transaction_type(item['transaction_type'])} "
                    f"of {FintechAgent._format_money(item['amount'])} "
                    f"(activity risk: {item['risk_level']})"
                    for item in transaction_history["transactions"]
                ]
                parts.append(
                    f"I found these recent transactions for "
                    f"{transaction_history['user_id']}: "
                    + "; ".join(formatted_transactions)
                    + ". If you want, ask me about one transaction ID and I’ll break it down."
                )
            else:
                parts.append(
                    f"I couldn’t find recent transactions for {transaction_history['user_id']}."
                )

        risk = results.get("risk")
        if risk and risk.get("found"):
            linked_transaction_id = risk.get("linked_transaction_id") or risk.get("transaction_id")
            account_label = risk.get("account_number") or risk.get("account_id")
            if risk.get("risk_scope") == "account_activity":
                if linked_transaction_id:
                    risk_subject = f"The account associated with {linked_transaction_id}"
                else:
                    risk_subject = f"Account {account_label}" if account_label else "This account"
                parts.append(
                    f"{risk_subject} currently has "
                    f"{risk['risk_level'].upper()} account activity risk because "
                    f"{'; '.join(risk['reasons'])}."
                )
            else:
                risk_subject = linked_transaction_id or f"account {account_label}"
                parts.append(
                    f"Here is the transaction risk read: {risk_subject} is "
                    f"{risk['risk_level'].upper()} risk because "
                    f"{'; '.join(risk['reasons'])}."
                )
            if risk.get("risk_score") is not None:
                parts.append(f"Activity-risk score: {risk['risk_score']}.")
            if risk["manual_review_required"]:
                parts.append(
                    "Because of that, it needs manual review and cannot be approved automatically."
                )

        faq = results.get("faq")
        if faq and faq.get("found"):
            parts.append(faq["answer"])

        ticket = results.get("ticket")
        if ticket:
            if ticket.get("created"):
                parts.append(
                    f"I’ve opened support ticket {ticket['ticket_id']} for you. "
                    f"It is currently {ticket['status']}."
                )
            else:
                parts.append(f"I couldn’t create the support ticket: {ticket['error']}.")

        if plan.intent == Intent.REFUND and not transaction_id:
            parts.append("Please provide the transaction ID so I can inspect the correct record.")
        elif plan.intent == Intent.TRANSACTION_STATUS and not transaction_id:
            parts.append(
                "Please provide the transaction ID, for example TXN1001, so I can "
                "check the exact payment record."
            )
        elif plan.intent == Intent.KYC and not user_id:
            parts.append("Please provide a user ID, or sign in as the customer whose KYC you need.")
        elif plan.intent == Intent.COMPLAINT and not user_id:
            parts.append("Please provide a valid transaction or user ID so I can open the case.")
        elif plan.intent == Intent.GENERAL_SUPPORT and not (faq and faq.get("found", False)):
            parts.append(
                "I’m focused on fintech support, so I do not want to guess outside the "
                "approved records. I can help with transactions, refunds, KYC, wallet "
                "issues, account activity risk, policies, or support tickets."
            )

        return " ".join(parts) or (
            "I can help with transactions, refunds, KYC, wallet issues, account activity risk, "
            "policies, and human support escalation."
        )
