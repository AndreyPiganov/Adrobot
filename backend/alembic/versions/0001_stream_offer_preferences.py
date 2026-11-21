"""Create storage for restored offers and pinned traffic shares."""

import sqlalchemy as sa
from alembic import op

revision = "0001_stream_offer_preferences"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "stream_offer_preferences",
        sa.Column("stream_id", sa.BigInteger(), nullable=False),
        sa.Column("offer_id", sa.BigInteger(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("stream_id", "offer_id"),
    )


def downgrade() -> None:
    op.drop_table("stream_offer_preferences")
