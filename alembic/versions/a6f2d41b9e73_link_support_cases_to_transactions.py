"""Link customer support cases to CoreBank transactions."""

import sqlalchemy as sa

from alembic import op

revision = "a6f2d41b9e73"
down_revision = "88a9c4b4197d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_case_transactions",
        sa.Column("ticket_id", sa.String(36), nullable=False),
        sa.Column("transaction_reference", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ticket_id"),
        sa.UniqueConstraint("transaction_reference", name="uq_support_case_transaction_reference"),
    )


def downgrade() -> None:
    op.drop_table("support_case_transactions")
