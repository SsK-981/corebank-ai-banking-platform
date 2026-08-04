"""Seed the Java CoreBank app with a demo admin, customers, and transactions.

Run this after the Spring Boot app is available at http://127.0.0.1:8080:

    python scripts/seed_corebank_demo.py

The script is intentionally idempotent-ish for demos: duplicate users/accounts are
treated as already seeded, and the script fetches existing accounts when possible.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("COREBANK_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
TIMEOUT = float(os.getenv("COREBANK_TIMEOUT_SECONDS", "8"))

DEMO_ADMIN = {
    "full_name": "Demo Administrator",
    "email": os.getenv("COREBANK_SEED_ADMIN_EMAIL", "demo.admin@corebank.local"),
    "password": os.getenv("COREBANK_SEED_ADMIN_PASSWORD", "password123"),
    "admin_code": os.getenv("COREBANK_SEED_ADMIN_CODE", "admin123"),
}

DEMO_USERS = [
    {
        "user_id": "U001",
        "full_name": "Rahul Sharma",
        "email": os.getenv("COREBANK_USER_U001_EMAIL", "rahul@example.com"),
        "password": os.getenv("COREBANK_SEED_USER_U001_PASSWORD", "password123"),
        "kyc_status": "VERIFIED",
        "initial_balance": Decimal("15000.00"),
    },
    {
        "user_id": "U002",
        "full_name": "Amit Verma",
        "email": os.getenv("COREBANK_USER_U002_EMAIL", "amit@example.com"),
        "password": os.getenv("COREBANK_SEED_USER_U002_PASSWORD", "password123"),
        "kyc_status": "PENDING",
        "initial_balance": Decimal("25000.00"),
    },
    {
        "user_id": "U003",
        "full_name": "Neha Patil",
        "email": os.getenv("COREBANK_USER_U003_EMAIL", "neha@example.com"),
        "password": os.getenv("COREBANK_SEED_USER_U003_PASSWORD", "password123"),
        "kyc_status": "VERIFIED",
        "initial_balance": Decimal("40000.00"),
    },
]


def request(
    method: str,
    path: str,
    *,
    auth: tuple[str, str] | None = None,
    json: dict[str, Any] | None = None,
) -> requests.Response:
    return requests.request(
        method,
        f"{BASE_URL}{path}",
        auth=auth,
        json=json,
        timeout=TIMEOUT,
    )


def page_content(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("content"), list):
        return payload["content"]
    if isinstance(payload, list):
        return payload
    return []


def register_user(user: dict[str, Any]) -> None:
    response = request(
        "POST",
        "/auth/customer/register",
        json={
            "fullName": user["full_name"],
            "email": user["email"],
            "password": user["password"],
            "adminCode": "",
        },
    )
    if response.status_code in {200, 201}:
        print(f"Registered {user['user_id']} ({user['email']})")
        return
    if response.status_code in {400, 409}:
        print(f"User {user['user_id']} already exists")
        return
    response.raise_for_status()


def register_admin() -> None:
    response = request(
        "POST",
        "/auth/admin/register",
        json={
            "fullName": DEMO_ADMIN["full_name"],
            "email": DEMO_ADMIN["email"],
            "password": DEMO_ADMIN["password"],
            "adminCode": DEMO_ADMIN["admin_code"],
        },
    )
    if response.status_code in {200, 201}:
        print(f"Registered demo admin ({DEMO_ADMIN['email']})")
        return
    if response.status_code in {400, 409}:
        print(f"Demo admin {DEMO_ADMIN['email']} already exists")
        return
    response.raise_for_status()


def update_kyc(user: dict[str, Any]) -> None:
    response = request(
        "PATCH",
        f"/admin/customers/{quote(user['email'], safe='')}/kyc",
        auth=(DEMO_ADMIN["email"], DEMO_ADMIN["password"]),
        json={"status": user["kyc_status"]},
    )
    response.raise_for_status()
    print(f"Set {user['user_id']} KYC to {user['kyc_status']}")


def list_accounts(user: dict[str, Any]) -> list[dict[str, Any]]:
    response = request(
        "GET",
        "/customer/accounts",
        auth=(user["email"], user["password"]),
    )
    response.raise_for_status()
    return page_content(response.json())


def create_or_get_account(user: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    existing = list_accounts(user)
    if existing:
        account = existing[0]
        print(f"{user['user_id']} already has account {account['accountNumber']}")
        return account, False

    response = request(
        "POST",
        "/customer/accounts",
        auth=(user["email"], user["password"]),
        json={
            "holderName": user["full_name"],
            "initialBalance": str(user["initial_balance"]),
        },
    )
    response.raise_for_status()
    account = response.json()
    print(f"Created account {account['accountNumber']} for {user['user_id']}")
    return account, True


def withdraw(user: dict[str, Any], account_id: int, amount: Decimal) -> None:
    response = request(
        "POST",
        f"/customer/accounts/{account_id}/withdraw",
        auth=(user["email"], user["password"]),
        json={"amount": str(amount)},
    )
    if response.status_code in {200, 201}:
        print(f"Withdrew ₹{amount} for {user['user_id']}")
    else:
        print(f"Withdrawal skipped for {user['user_id']}: {response.text[:120]}")


def transfer(
    user: dict[str, Any],
    from_account_id: int,
    to_account_number: str,
    amount: Decimal,
) -> None:
    response = request(
        "POST",
        "/customer/accounts/transfer",
        auth=(user["email"], user["password"]),
        json={
            "fromAccountId": from_account_id,
            "toAccountNumber": to_account_number,
            "amount": str(amount),
        },
    )
    if response.status_code in {200, 201}:
        print(f"Transferred ₹{amount} from {user['user_id']}")
    else:
        print(f"Transfer skipped for {user['user_id']}: {response.text[:120]}")


def main() -> int:
    health = requests.get(f"{BASE_URL}/accounts/health", timeout=TIMEOUT)
    health.raise_for_status()
    print(f"Connected to CoreBank: {health.text}")

    register_admin()

    for user in DEMO_USERS:
        register_user(user)
        update_kyc(user)

    account_results = {user["user_id"]: create_or_get_account(user) for user in DEMO_USERS}
    accounts = {user_id: result[0] for user_id, result in account_results.items()}
    if any(result[1] for result in account_results.values()):
        withdraw(DEMO_USERS[1], accounts["U002"]["accountId"], Decimal("1200.00"))
        withdraw(DEMO_USERS[1], accounts["U002"]["accountId"], Decimal("100000.00"))
        transfer(
            DEMO_USERS[1],
            accounts["U002"]["accountId"],
            accounts["U001"]["accountNumber"],
            Decimal("750.00"),
        )
        transfer(
            DEMO_USERS[2],
            accounts["U003"]["accountId"],
            accounts["U002"]["accountNumber"],
            Decimal("1500.00"),
        )
    else:
        print("Demo transactions already exist; transaction seeding skipped")

    print("")
    print("CoreBank demo data is ready.")
    print(f"Demo admin: {DEMO_ADMIN['email']} / {DEMO_ADMIN['password']}")
    print("Now set BANKING_DATA_SOURCE=corebank in .env and restart the chatbot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
