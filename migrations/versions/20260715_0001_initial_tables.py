"""Create initial Machine Document Portal tables.

Revision ID: 20260715_0001
Revises:
Create Date: 2026-07-15 14:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "machines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("machine_id", sa.String(length=32), nullable=False),
        sa.Column("group_name", sa.String(length=32), nullable=False),
        sa.Column("machine_number", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("group_color", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_machines")),
        sa.UniqueConstraint("machine_id", name=op.f("uq_machines_machine_id")),
    )
    op.create_index("ix_machines_display_order", "machines", ["display_order"], unique=False)

    op.create_table(
        "document_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("part_number", sa.String(length=128), nullable=False),
        sa.Column("normalized_part_number", sa.String(length=128), nullable=False),
        sa.Column("inspection_url", sa.Text(), nullable=True),
        sa.Column("drawing_url", sa.Text(), nullable=True),
        sa.Column("inspection_status", sa.String(length=32), nullable=False),
        sa.Column("drawing_status", sa.String(length=32), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_links")),
    )
    op.create_index(
        "ix_document_links_normalized_part_number",
        "document_links",
        ["normalized_part_number"],
        unique=False,
    )

    op.create_table(
        "sync_histories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sync_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_histories")),
    )

    op.create_table(
        "current_productions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("machine_id", sa.Integer(), nullable=False),
        sa.Column("part_number", sa.String(length=128), nullable=True),
        sa.Column("normalized_part_number", sa.String(length=128), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("production_status", sa.String(length=64), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["machine_id"], ["machines.id"], name=op.f("fk_current_productions_machine_id_machines"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_current_productions")),
        sa.UniqueConstraint("machine_id", name=op.f("uq_current_productions_machine_id")),
    )
    op.create_index(
        "ix_current_productions_normalized_part_number",
        "current_productions",
        ["normalized_part_number"],
        unique=False,
    )

    op.create_table(
        "document_candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_link_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_file_id", sa.String(length=255), nullable=True),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_link_id"], ["document_links.id"], name=op.f("fk_document_candidates_document_link_id_document_links"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_candidates")),
    )


def downgrade() -> None:
    op.drop_table("document_candidates")
    op.drop_index("ix_current_productions_normalized_part_number", table_name="current_productions")
    op.drop_table("current_productions")
    op.drop_table("sync_histories")
    op.drop_index("ix_document_links_normalized_part_number", table_name="document_links")
    op.drop_table("document_links")
    op.drop_index("ix_machines_display_order", table_name="machines")
    op.drop_table("machines")
