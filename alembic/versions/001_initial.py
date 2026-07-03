"""Initial schema: users, auctions, bids, proxy_bids.

Revision ID: 001
Revises: None
Create Date: 2026-07-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the four core tables."""

    # ── User ─────────────────────────────────────────────────────
    op.create_table(
        "user",
        sa.Column(
            "user_id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("email"),
    )

    # ── Auction ──────────────────────────────────────────────────
    op.create_table(
        "auction",
        sa.Column(
            "auction_id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("seller_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("starting_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("reserve_price", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "min_increment", sa.Numeric(12, 2), nullable=False, server_default=sa.text("1.00")
        ),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default=sa.text("'UPCOMING'")),
        sa.Column("highest_bid", sa.Numeric(12, 2), nullable=True),
        sa.Column("winner_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("auction_id"),
        sa.ForeignKeyConstraint(["seller_id"], ["user.user_id"], name="fk_auction_seller_id_user"),
        sa.ForeignKeyConstraint(["winner_id"], ["user.user_id"], name="fk_auction_winner_id_user"),
    )
    op.create_index("ix_auction_state", "auction", ["state"])
    op.create_index("ix_auction_category", "auction", ["category"])
    op.create_index("ix_auction_end_ts", "auction", ["end_ts"])
    op.create_index("ix_auction_seller_id", "auction", ["seller_id"])

    # ── Bid ──────────────────────────────────────────────────────
    op.create_table(
        "bid",
        sa.Column("bid_id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("auction_id", sa.UUID(), nullable=False),
        sa.Column("bidder_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_proxy", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sequence_num", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'ACCEPTED'")),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("bid_id"),
        sa.ForeignKeyConstraint(
            ["auction_id"], ["auction.auction_id"], name="fk_bid_auction_id_auction"
        ),
        sa.ForeignKeyConstraint(["bidder_id"], ["user.user_id"], name="fk_bid_bidder_id_user"),
        sa.UniqueConstraint("auction_id", "bidder_id", "amount", "created_ts", name="uq_bid_dedup"),
    )
    op.create_index("ix_bid_auction_id_seq", "bid", ["auction_id", sa.text("sequence_num DESC")])
    op.create_index("ix_bid_bidder_id", "bid", ["bidder_id"])

    # ── ProxyBid ─────────────────────────────────────────────────
    op.create_table(
        "proxy_bid",
        sa.Column(
            "proxy_id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("auction_id", sa.UUID(), nullable=False),
        sa.Column("bidder_id", sa.UUID(), nullable=False),
        sa.Column("max_bid", sa.Numeric(12, 2), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "entered_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("proxy_id"),
        sa.ForeignKeyConstraint(
            ["auction_id"], ["auction.auction_id"], name="fk_proxy_bid_auction_id_auction"
        ),
        sa.ForeignKeyConstraint(
            ["bidder_id"], ["user.user_id"], name="fk_proxy_bid_bidder_id_user"
        ),
        sa.UniqueConstraint("auction_id", "bidder_id", name="uq_proxy_bid_auction_bidder"),
    )


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table("proxy_bid")
    op.drop_table("bid")
    op.drop_table("auction")
    op.drop_table("user")
