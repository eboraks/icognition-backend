"""Add research_session table and research_session_id on document

Adds the research_session table for tracking research agent runs and a
research_session_id foreign key on document linking docs created during
a research run.

Revision ID: j2k3l4m5n6o7
Revises: i1j2k3l4m5n6
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = "j2k3l4m5n6o7"
down_revision: Union[str, Sequence[str], None] = "i1j2k3l4m5n6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- research_session ---
    op.create_table(
        "research_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("chat_session_id", sa.Integer(), nullable=True),
        sa.Column("chat_message_id", sa.Integer(), nullable=True),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column("plan", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("budget", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False, server_default="running"),
        sa.Column("final_response", sa.Text(), nullable=True),
        sa.Column("token_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"]),
        sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_research_session_user_id"), "research_session", ["user_id"])

    # --- document.research_session_id ---
    op.add_column(
        "document",
        sa.Column("research_session_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_research_session_id",
        "document",
        "research_session",
        ["research_session_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_document_research_session_id"),
        "document",
        ["research_session_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_research_session_id"), table_name="document")
    op.drop_constraint("fk_document_research_session_id", "document", type_="foreignkey")
    op.drop_column("document", "research_session_id")

    op.drop_index(op.f("ix_research_session_user_id"), table_name="research_session")
    op.drop_table("research_session")
