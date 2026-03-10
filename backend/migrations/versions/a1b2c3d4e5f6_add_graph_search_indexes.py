"""Add pg_trgm extension and GIN indexes for graph search

Revision ID: a1b2c3d4e5f6
Revises: 17da34c28575
Create Date: 2026-03-04
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '17da34c28575'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable trigram extension for fuzzy search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # GIN indexes for fuzzy search
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_name_trgm "
        "ON entities USING GIN (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rel_type_trgm "
        "ON entity_relationships USING GIN (relationship_type gin_trgm_ops)"
    )

    # B-tree indexes on entity_documents join table
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_entdoc_entity "
        "ON entity_documents (entity_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_entdoc_document "
        "ON entity_documents (document_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_entdoc_document")
    op.execute("DROP INDEX IF EXISTS idx_entdoc_entity")
    op.execute("DROP INDEX IF EXISTS idx_rel_type_trgm")
    op.execute("DROP INDEX IF EXISTS idx_entity_name_trgm")
