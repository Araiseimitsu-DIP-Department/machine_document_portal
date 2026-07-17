"""Seed the initial machine master records.

Revision ID: 20260716_0002
Revises: 20260715_0001
Create Date: 2026-07-16 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260716_0002"
down_revision: str | None = "20260715_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_GROUPS = (
    ("A", 5, "#1e88e5"),
    ("B", 4, "#008c9e"),
    ("C", 12, "#6473d9"),
    ("D", 12, "#8b63c7"),
    ("E", 14, "#d17b25"),
    ("F", 14, "#3b8d69"),
)


def _machine_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    display_order = 0
    for group_name, count, group_color in _GROUPS:
        for machine_number in range(1, count + 1):
            display_order += 1
            rows.append(
                {
                    "machine_id": f"{group_name}-{machine_number}",
                    "group_name": group_name,
                    "machine_number": machine_number,
                    "display_order": display_order,
                    "group_color": group_color,
                    "enabled": True,
                }
            )
    return rows


def upgrade() -> None:
    machines = sa.table(
        "machines",
        sa.column("machine_id", sa.String),
        sa.column("group_name", sa.String),
        sa.column("machine_number", sa.Integer),
        sa.column("display_order", sa.Integer),
        sa.column("group_color", sa.String),
        sa.column("enabled", sa.Boolean),
    )
    op.bulk_insert(machines, _machine_rows())


def downgrade() -> None:
    machine_ids = [row["machine_id"] for row in _machine_rows()]
    op.execute(sa.delete(sa.table("machines", sa.column("machine_id", sa.String))).where(
        sa.column("machine_id", sa.String).in_(machine_ids)
    ))
