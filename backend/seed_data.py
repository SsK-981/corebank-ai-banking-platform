"""Idempotently seed the demo database from the sample CSV files."""

from pathlib import Path

import pandas as pd
from sqlalchemy import select

from backend.database import SessionLocal, init_db
from backend.models import FAQ, Transaction, User
from backend.risk_engine import score_transaction

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def seed_database() -> None:
    """Create tables and load sample records only when each table is empty."""
    init_db()

    with SessionLocal() as db:
        if db.scalar(select(User.id).limit(1)) is None:
            users = pd.read_csv(DATA_DIR / "sample_users.csv").to_dict("records")
            db.add_all([User(**row) for row in users])
            db.flush()

        if db.scalar(select(Transaction.id).limit(1)) is None:
            transactions = pd.read_csv(DATA_DIR / "sample_transactions.csv").to_dict("records")
            db.add_all([Transaction(**row) for row in transactions])

        if db.scalar(select(FAQ.id).limit(1)) is None:
            faqs = pd.read_csv(DATA_DIR / "sample_faq.csv").to_dict("records")
            db.add_all([FAQ(**row) for row in faqs])

        db.commit()

        # Keep the stored risk level aligned with the explainable rules.
        users_by_id = {user.user_id: user for user in db.scalars(select(User)).all()}
        for transaction in db.scalars(select(Transaction)).all():
            user = users_by_id.get(transaction.user_id)
            if user:
                result = score_transaction(
                    transaction.amount,
                    transaction.failed_attempts,
                    user.kyc_status,
                )
                transaction.risk_level = result["risk_level"]
        db.commit()


if __name__ == "__main__":
    seed_database()
    print("Database seeded successfully.")
