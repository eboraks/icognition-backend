"""Add relationship_documents junction table, deduplicate relationships, normalize entity types

Revision ID: g1h2i3j4k5l6
Revises: b2c3d4e5f6a7
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'g1h2i3j4k5l6'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Step 1: Create relationship_documents junction table ---
    op.create_table(
        'relationship_documents',
        sa.Column('relationship_id', sa.Integer(), sa.ForeignKey('entity_relationships.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('document.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_reldocs_document_id', 'relationship_documents', ['document_id'])

    # --- Step 2: Migrate existing source_document_id data ---
    op.execute("""
        INSERT INTO relationship_documents (relationship_id, document_id)
        SELECT id, source_document_id
        FROM entity_relationships
        WHERE source_document_id IS NOT NULL
    """)

    # --- Step 3: Deduplicate entity_relationships ---
    # 3a: Remap junction table entries from duplicate relationships to keepers
    op.execute("""
        WITH keepers AS (
            SELECT MIN(id) AS keep_id, from_entity_id, to_entity_id, relationship_type
            FROM entity_relationships
            GROUP BY from_entity_id, to_entity_id, relationship_type
        ),
        dupes AS (
            SELECT er.id AS dupe_id, k.keep_id
            FROM entity_relationships er
            JOIN keepers k ON er.from_entity_id = k.from_entity_id
                          AND er.to_entity_id = k.to_entity_id
                          AND er.relationship_type = k.relationship_type
            WHERE er.id != k.keep_id
        )
        UPDATE relationship_documents rd
        SET relationship_id = d.keep_id
        FROM dupes d
        WHERE rd.relationship_id = d.dupe_id
    """)

    # 3b: Remove duplicate junction entries (same relationship_id + document_id)
    op.execute("""
        DELETE FROM relationship_documents a
        USING relationship_documents b
        WHERE a.ctid > b.ctid
          AND a.relationship_id = b.relationship_id
          AND a.document_id = b.document_id
    """)

    # 3c: Delete duplicate relationship rows (keep min id per group)
    op.execute("""
        DELETE FROM entity_relationships
        WHERE id NOT IN (
            SELECT MIN(id) FROM entity_relationships
            GROUP BY from_entity_id, to_entity_id, relationship_type
        )
    """)

    # --- Step 4: Drop old column and add unique constraint ---
    op.drop_index('ix_entity_rel_unique', table_name='entity_relationships')
    op.drop_index('ix_entity_relationships_source_document_id', table_name='entity_relationships')
    op.drop_column('entity_relationships', 'source_document_id')
    op.create_index(
        'ix_entity_rel_unique',
        'entity_relationships',
        ['from_entity_id', 'to_entity_id', 'relationship_type'],
        unique=True
    )

    # --- Step 5: Normalize entity types to lowercase ---
    op.execute("UPDATE entities SET type = LOWER(type) WHERE type != LOWER(type)")

    # Also normalize relationship_type to lowercase for consistency
    op.execute("UPDATE entity_relationships SET relationship_type = LOWER(relationship_type) WHERE relationship_type != LOWER(relationship_type)")


def downgrade() -> None:
    # Re-add source_document_id column
    op.add_column('entity_relationships', sa.Column('source_document_id', sa.Integer(), sa.ForeignKey('document.id'), nullable=True))
    op.create_index('ix_entity_relationships_source_document_id', 'entity_relationships', ['source_document_id'])

    # Restore data from junction table (pick one document per relationship)
    op.execute("""
        UPDATE entity_relationships er
        SET source_document_id = rd.document_id
        FROM (
            SELECT DISTINCT ON (relationship_id) relationship_id, document_id
            FROM relationship_documents
            ORDER BY relationship_id, document_id
        ) rd
        WHERE er.id = rd.relationship_id
    """)

    # Recreate old unique index
    op.drop_index('ix_entity_rel_unique', table_name='entity_relationships')
    op.create_index(
        'ix_entity_rel_unique',
        'entity_relationships',
        ['from_entity_id', 'to_entity_id', 'relationship_type', 'source_document_id'],
        unique=True
    )

    # Drop junction table
    op.drop_index('ix_reldocs_document_id', table_name='relationship_documents')
    op.drop_table('relationship_documents')
