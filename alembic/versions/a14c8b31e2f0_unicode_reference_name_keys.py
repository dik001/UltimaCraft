"""unicode reference name keys

Revision ID: a14c8b31e2f0
Revises: 90b4640735d1
Create Date: 2026-08-28 01:08:00
"""
from __future__ import annotations

import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a14c8b31e2f0"
down_revision: str | None = "90b4640735d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLES = (
    "acquisition_method",
    "craft_station",
    "equipment",
    "item_group",
    "item_subgroup",
    "skill",
)


def _key(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()


def upgrade() -> None:
    connection = op.get_bind()
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("name_key", sa.String(length=240), nullable=False, server_default=""),
        )
        rows = connection.execute(sa.text(f"SELECT id, name FROM {table}")).mappings()
        for row in rows:
            connection.execute(
                sa.text(f"UPDATE {table} SET name_key = :key WHERE id = :id"),
                {"key": _key(row["name"]), "id": row["id"]},
            )

    op.create_index("ux_acquisition_method_name_key", "acquisition_method", ["name_key"], unique=True)
    op.create_index("ux_craft_station_name_key", "craft_station", ["name_key"], unique=True)
    op.create_index("ux_equipment_name_key", "equipment", ["name_key"], unique=True)
    op.create_index("ux_item_group_name_key", "item_group", ["name_key"], unique=True)
    op.create_index(
        "ux_item_subgroup_group_name_key",
        "item_subgroup",
        ["group_id", "name_key"],
        unique=True,
    )
    op.create_index("ux_skill_name_key", "skill", ["name_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_skill_name_key", table_name="skill")
    op.drop_index("ux_item_subgroup_group_name_key", table_name="item_subgroup")
    op.drop_index("ux_item_group_name_key", table_name="item_group")
    op.drop_index("ux_equipment_name_key", table_name="equipment")
    op.drop_index("ux_craft_station_name_key", table_name="craft_station")
    op.drop_index("ux_acquisition_method_name_key", table_name="acquisition_method")
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("name_key")

