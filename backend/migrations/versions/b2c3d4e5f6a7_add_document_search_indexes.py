"""Add GIN trigram indexes on document.title and document.ai_markdown_content for graph search

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-05
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # GIN trigram index on document.title for fuzzy search
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_title_trgm "
        "ON document USING GIN (title gin_trgm_ops)"
    )
    # GIN trigram index on document.ai_markdown_content for fuzzy search
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_ai_markdown_trgm "
        "ON document USING GIN (ai_markdown_content gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_document_ai_markdown_trgm")
    op.execute("DROP INDEX IF EXISTS idx_document_title_trgm")
