"""HTTP client for the Java Spring Boot CoreBank application.

The chatbot uses this adapter instead of reading the banking database directly.
That keeps the architecture realistic: the AI layer calls authorized banking APIs,
and CoreBank remains the system of record for accounts, balances, transactions,
and risk insights.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import quote

import requests

from backend.config import Settings, get_settings


class CoreBankError(RuntimeError):
    """Base class for CoreBank integration failures."""


class CoreBankUnavailable(CoreBankError):
    """Raised when CoreBank cannot be reached or returns an unexpected response."""


class CoreBankAccessDenied(CoreBankError):
    """Raised when CoreBank rejects the mapped customer credentials."""


class CoreBankClient:
    """Small, typed adapter over the Spring Boot banking API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = requests.Session()

    def _customer_path(self, user_id: str) -> str:
        email = self.settings.corebank_email_for(user_id)
        if email is None:
            raise CoreBankAccessDenied(f"No CoreBank customer mapping is configured for {user_id}")
        return f"/internal/ai/customers/{quote(email, safe='')}"

    def _request(
        self,
        user_id: str,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.settings.corebank_base_url}{path}"
        try:
            response = self.session.request(
                method,
                url,
                headers={
                    "X-CoreBank-Service-Token": self.settings.corebank_service_token,
                    "Accept": "application/json",
                },
                params=params,
                json=json,
                timeout=self.settings.corebank_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise CoreBankUnavailable(f"CoreBank is unavailable at {url}") from exc

        if response.status_code in {401, 403}:
            raise CoreBankAccessDenied("CoreBank denied access for the mapped customer")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise CoreBankUnavailable(f"CoreBank returned HTTP {response.status_code} for {path}")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise CoreBankUnavailable(f"CoreBank returned non-JSON data for {path}") from exc

    @staticmethod
    def _page_content(payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            content = payload.get("content", [])
            if isinstance(content, list):
                return [item for item in content if isinstance(item, dict)]
        raise CoreBankUnavailable("CoreBank returned an unexpected page shape")

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        return Decimal(str(value or "0"))

    @staticmethod
    def _transaction_status(transaction_type: str, description: str) -> str:
        lowered = f"{transaction_type} {description}".lower()
        if "failed" in lowered or "rejected" in lowered:
            return "failed"
        return "posted"

    @staticmethod
    def _normalize_account(account: dict[str, Any]) -> dict[str, Any]:
        return {
            "account_id": account.get("accountId"),
            "account_number": account.get("accountNumber"),
            "holder_name": account.get("holderName"),
            "balance": CoreBankClient._decimal(account.get("balance")),
            "active": bool(account.get("active", True)),
            "owner_email": account.get("ownerEmail"),
        }

    @staticmethod
    def _normalize_transaction(
        transaction: dict[str, Any],
        account: dict[str, Any],
        user_id: str,
    ) -> dict[str, Any]:
        transaction_type = str(transaction.get("type") or "TRANSACTION")
        description = str(transaction.get("description") or "")
        explicit_status = str(transaction.get("status") or "").lower()
        transaction_id = str(
            transaction.get("referenceNumber") or f"TXN{transaction.get('id', '')}"
        ).upper()
        return {
            "found": True,
            "transaction_id": transaction_id,
            "reference_number": transaction_id,
            "corebank_transaction_id": transaction.get("id"),
            "user_id": user_id.upper(),
            "account_id": account.get("account_id"),
            "account_number": account.get("account_number"),
            "status": explicit_status
            if explicit_status in {"posted", "failed"}
            else CoreBankClient._transaction_status(transaction_type, description),
            "amount": CoreBankClient._decimal(transaction.get("amount")),
            "transaction_type": transaction_type.lower(),
            "description": description,
            "failure_reason": transaction.get("failureReason"),
            "timestamp": transaction.get("timestamp"),
            "failed_attempts": 0,
            "risk_level": "unknown",
            "source": "corebank",
        }

    def current_customer_profile(self, user_id: str) -> dict[str, Any]:
        payload = self._request(user_id, "GET", f"{self._customer_path(user_id)}/profile")
        if not isinstance(payload, dict):
            raise CoreBankUnavailable("CoreBank returned an unexpected profile shape")
        return {
            "found": True,
            "user_id": user_id.upper(),
            "customer_id": payload.get("id"),
            "full_name": payload.get("fullName"),
            "role": str(payload.get("role") or "CUSTOMER"),
            "kyc_status": str(payload.get("kycStatus") or "NOT_AVAILABLE").lower(),
            "source": "corebank",
        }

    def list_accounts(self, user_id: str, limit: int = 20) -> dict[str, Any]:
        payload = self._request(
            user_id,
            "GET",
            f"{self._customer_path(user_id)}/accounts",
            params={"size": max(1, min(limit, 50))},
        )
        accounts = [self._normalize_account(item) for item in self._page_content(payload)]
        return {
            "found": bool(accounts),
            "user_id": user_id.upper(),
            "accounts": accounts,
            "source": "corebank",
        }

    def account_summary(self, user_id: str) -> dict[str, Any]:
        profile = self.current_customer_profile(user_id)
        accounts_result = self.list_accounts(user_id)
        accounts = accounts_result["accounts"]
        total_balance = sum((account["balance"] for account in accounts), Decimal("0"))
        active_accounts = sum(1 for account in accounts if account["active"])
        return {
            "found": bool(accounts),
            "user_id": user_id.upper(),
            "profile": profile,
            "accounts": accounts,
            "total_balance": total_balance,
            "active_accounts": active_accounts,
            "source": "corebank",
        }

    def _account_for_transaction(
        self,
        user_id: str,
        account_id: int | None = None,
    ) -> list[dict[str, Any]]:
        accounts = self.list_accounts(user_id)["accounts"]
        if account_id is None:
            return accounts
        return [account for account in accounts if account["account_id"] == account_id]

    def list_transactions(
        self,
        user_id: str,
        *,
        account_id: int | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(limit, 50))
        transactions: list[dict[str, Any]] = []
        for account in self._account_for_transaction(user_id, account_id):
            payload = self._request(
                user_id,
                "GET",
                f"{self._customer_path(user_id)}/accounts/{account['account_id']}/transactions",
                params={"size": safe_limit},
            )
            transactions.extend(
                self._normalize_transaction(item, account, user_id)
                for item in self._page_content(payload)
            )

        transactions.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        return {
            "found": bool(transactions),
            "user_id": user_id.upper(),
            "transactions": transactions[:safe_limit],
            "source": "corebank",
        }

    def get_transaction(self, user_id: str, transaction_id: str) -> dict[str, Any]:
        normalized = transaction_id.strip().upper()
        transactions = self.list_transactions(user_id, limit=50)["transactions"]
        for transaction in transactions:
            if (
                transaction["transaction_id"].upper() == normalized
                or str(transaction.get("corebank_transaction_id")) == normalized
            ):
                return transaction
        return {
            "found": False,
            "transaction_id": normalized,
            "user_id": user_id.upper(),
            "source": "corebank",
        }

    def risk_insights(
        self,
        user_id: str,
        *,
        account_id: int | None = None,
        transaction_id: str | None = None,
    ) -> dict[str, Any]:
        selected_account_id = account_id
        if transaction_id and selected_account_id is None:
            transaction = self.get_transaction(user_id, transaction_id)
            if not transaction.get("found"):
                return {
                    "found": False,
                    "transaction_id": transaction_id.upper(),
                    "user_id": user_id.upper(),
                    "source": "corebank",
                }
            selected_account_id = transaction["account_id"]

        if selected_account_id is None:
            accounts = self.list_accounts(user_id)["accounts"]
            if not accounts:
                return {"found": False, "user_id": user_id.upper(), "source": "corebank"}
            selected_account_id = accounts[0]["account_id"]

        payload = self._request(
            user_id,
            "GET",
            f"{self._customer_path(user_id)}/accounts/{selected_account_id}/risk-insights",
        )
        if not isinstance(payload, dict):
            raise CoreBankUnavailable("CoreBank returned an unexpected risk-insight shape")

        signals = payload.get("signals", [])
        if not isinstance(signals, list):
            signals = []
        reasons = [
            f"{signal.get('title')}: {signal.get('detail')}"
            for signal in signals
            if isinstance(signal, dict)
        ]
        risk_level = str(payload.get("riskLevel") or "UNKNOWN").lower()
        return {
            "found": True,
            "transaction_id": transaction_id.upper() if transaction_id else None,
            "user_id": user_id.upper(),
            "account_id": payload.get("accountId"),
            "account_number": payload.get("accountNumber"),
            "risk_level": risk_level,
            "risk_score": payload.get("riskScore", 0),
            "current_balance": self._decimal(payload.get("currentBalance")),
            "total_credits": self._decimal(payload.get("totalCredits")),
            "total_debits": self._decimal(payload.get("totalDebits")),
            "largest_transaction": self._decimal(payload.get("largestTransaction")),
            "transaction_count": payload.get("transactionCount", 0),
            "reasons": reasons or [str(payload.get("recommendation") or "No risk signals")],
            "recommendation": payload.get("recommendation"),
            "manual_review_required": risk_level == "high",
            "source": "corebank",
        }
