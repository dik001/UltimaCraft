"""item unicode search key

Revision ID: c70fa293dc11
Revises: a14c8b31e2f0
Create Date: 2026-08-28 01:25:00
"""
from __future__ import annotations

import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c70fa293dc11"
down_revision: str | None = "a14c8b31e2f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    op.add_column(
        "item",
        sa.Column("name_key", sa.String(length=300), nullable=False, server_default=""),
    )
    rows = connection.execute(sa.text("SELECT id, name FROM item")).mappings()
    for row in rows:
        key = unicodedata.normalize("NFKC", row["name"].strip()).casefold()
        connection.execute(
            sa.text("UPDATE item SET name_key = :key WHERE id = :id"),
            {"key": key, "id": row["id"]},
        )
    op.create_index("ix_item_name_key", "item", ["name_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_item_name_key", table_name="item")
    with op.batch_alter_table("item") as batch_op:
        batch_op.drop_column("name_key")

